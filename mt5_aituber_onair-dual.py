#!/usr/bin/env python3
"""
MetaTrader 5 → AItuber on Air 統合システム (キュー実装・完全版)
"""

import asyncio
import json
import logging
import websockets
from dataclasses import dataclass, field
from typing import Dict, Set, Optional
import MetaTrader5 as mt5
from datetime import datetime
from aiohttp import web

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# ==================== 設定 ====================
@dataclass
class Config:
    watch_symbols: Dict[str, Dict] = field(default_factory=lambda: {
        "USDJPY": {"digits": 3, "jp_name": "どるえん"},
        "EURUSD": {"digits": 5, "jp_name": "ユーロドル"},
        "GBPUSD": {"digits": 5, "jp_name": "ポンドル"},
        "EURJPY": {"digits": 3, "jp_name": "ユーロえん"},
        "GBPJPY": {"digits": 3, "jp_name": "ポンドえん"},
    })
    update_interval: float = 2.0
    small_threshold: float = 5.0
    medium_threshold: float = 16.0
    large_threshold: float = 30.0
    msg_small: str = "📊 すこしうごきがあったぞ"
    msg_medium: str = "⚠️ ちゅうくらいのうごきがあったぞ"
    msg_large: str = "🚨 おい！なんかあったぞ"

    ws_host: str = "0.0.0.0"
    ws_port: int = 8000
    http_port: int = 8080
    
    # ★追加: 次の発言までの待機時間（秒）
    # 音声が被らないように、1回発言したらこの秒数だけ休みます
    speech_interval: float = 7.0 

config = Config()

# ★追加: 発言順番待ちキュー
speech_queue = asyncio.Queue()

# ==================== メッセージブローカー ====================
class MessageBroker:
    def __init__(self):
        self.clients: Set[websockets.WebSocketServerProtocol] = set()
        self.dashboard_clients: Set[websockets.WebSocketServerProtocol] = set()
    
    def add_client(self, ws: websockets.WebSocketServerProtocol, is_dashboard=False):
        if is_dashboard:
            self.dashboard_clients.add(ws)
            logger.info(f"✓ ダッシュボード接続 (合計: {len(self.dashboard_clients)})")
        else:
            self.clients.add(ws)
            logger.info(f"✓ AITuber接続 (合計: {len(self.clients)})")
    
    def remove_client(self, ws: websockets.WebSocketServerProtocol, is_dashboard=False):
        if is_dashboard:
            self.dashboard_clients.discard(ws)
        else:
            self.clients.discard(ws)
    
    async def broadcast(self, message_data):
        """AITuberへ送信する（キュー処理から呼ばれる）"""
        if not self.clients:
            return
        
        # JSON整形
        if isinstance(message_data, str):
            payload = {"type": "chat", "text": message_data}
        elif isinstance(message_data, dict):
            payload = message_data
            if "type" not in payload:
                payload["type"] = "chat"
                payload["text"] = payload.get("text", str(message_data))
        else:
            payload = {"type": "chat", "text": str(message_data)}

        message_to_send = json.dumps(payload, ensure_ascii=False)
        
        dead = set()
        for client in self.clients.copy():
            try:
                await client.send(message_to_send)
                display_text = payload.get('text', '')[:50]
                logger.info(f"🎤 発話送信: {display_text}...")
            except websockets.exceptions.ConnectionClosed:
                dead.add(client)
        
        for client in dead:
            self.remove_client(client)
    
    async def broadcast_dashboard(self, data: Dict):
        """ダッシュボード更新（これは即時送信でOK）"""
        if not self.dashboard_clients: return
        msg = json.dumps(data, ensure_ascii=False)
        dead = set()
        for client in self.dashboard_clients:
            try: await client.send(msg)
            except: dead.add(client)
        for client in dead: self.remove_client(client, is_dashboard=True)

broker = MessageBroker()

# ==================== ★追加: キュー処理ワーカー ====================
async def speech_worker():
    """キューに溜まったメッセージを順番に処理する"""
    logger.info("🗣️ 音声管理システム起動")
    while True:
        # キューからメッセージを取り出す（空なら待つ）
        message_data = await speech_queue.get()
        
        # メッセージを送信
        await broker.broadcast(message_data)
        
        # 処理完了を通知
        speech_queue.task_done()
        
        # ★重要: 次の発言まで待機（音声被り防止）
        # メッセージの長さによって待機時間を変えるとさらに良いですが
        # まずは固定値で安定させます。
        await asyncio.sleep(config.speech_interval)

# ==================== 価格監視 ====================
class PriceMonitor:
    def __init__(self):
        self.symbol_data = {}
        for symbol, info in config.watch_symbols.items():
            self.symbol_data[symbol] = {
                "base_price": None,
                "last_price": None,
                "digits": info["digits"],
                "jp_name": info["jp_name"]
            }
    
    def calculate_pips(self, symbol, price_change):
        digits = self.symbol_data[symbol]["digits"]
        if digits == 3 or digits == 5: pip_val = 0.1 ** (digits - 1)
        else: pip_val = 0.1 ** (digits - 2)
        return abs(price_change) / pip_val
    
    async def update_price(self, symbol, price):
        if symbol not in config.watch_symbols: return
        
        digits = self.symbol_data[symbol]["digits"]
        jp_name = self.symbol_data[symbol]["jp_name"]
        
        if self.symbol_data[symbol]["base_price"] is None:
            self.symbol_data[symbol]["base_price"] = price
            self.symbol_data[symbol]["last_price"] = price
            return
        
        base_price = self.symbol_data[symbol]["base_price"]
        price_change = price - base_price
        pips_change = self.calculate_pips(symbol, price_change)
        
        level_msg = None
        
        if pips_change >= config.large_threshold:
            level_msg = config.msg_large
            emotion_tag = "[surprised]"
        elif pips_change >= config.medium_threshold:
            level_msg = config.msg_medium
            emotion_tag = "[happy]" if price_change > 0 else "[neutral]"
        elif pips_change >= config.small_threshold:
            level_msg = config.msg_small
            emotion_tag = "[happy]" if price_change > 0 else "[neutral]"

        if level_msg:
            direction = "上昇" if price_change > 0 else "下降"
            message_text = f"{emotion_tag} {jp_name} が {pips_change:.1f} pips {direction} した。{level_msg}"
            
            logger.info(f"★ 変動検知: {symbol} (キューに追加)")
            
            # ★修正: 直接ブロードキャストせず、キューに入れる
            await speech_queue.put(message_text)
            
            self.symbol_data[symbol]["base_price"] = price
        
        self.symbol_data[symbol]["last_price"] = price
        await broker.broadcast_dashboard({
            "type": "price_update", "symbol": symbol, "jp_name": jp_name,
            "price": price, "base_price": base_price, "pips_change": pips_change
        })
    
    def get_status(self):
        status = []
        for symbol, data in self.symbol_data.items():
            status.append({
                "symbol": symbol, "jp_name": data["jp_name"],
                "price": data["last_price"], "base_price": data["base_price"]
            })
        return status

monitor = PriceMonitor()

# ==================== MT5クライアント ====================
class MT5Client:
    def __init__(self):
        self.running = False
        self.connected = False
    
    def connect(self):
        if not mt5.initialize():
            logger.error("✗ MT5初期化失敗")
            return False
        
        self.available_symbols = []
        for symbol in config.watch_symbols.keys():
            if mt5.symbol_select(symbol, True):
                self.available_symbols.append(symbol)
        
        if not self.available_symbols: return False
        self.connected = True
        return True
    
    async def start_monitoring(self):
        if not self.connected: return
        logger.info("✓ 価格監視ループ開始")
        self.running = True
        
        # 開始メッセージもキューへ
        jp_names = [config.watch_symbols[s]["jp_name"] for s in self.available_symbols]
        await speech_queue.put(f"[happy] 監視を開始しました。{len(jp_names)}通貨ペアを見ています")
        
        while self.running:
            try:
                for symbol in self.available_symbols:
                    tick = mt5.symbol_info_tick(symbol)
                    if tick: await monitor.update_price(symbol, tick.bid)
                await asyncio.sleep(config.update_interval)
            except Exception as e:
                logger.error(f"監視エラー: {e}")
                await asyncio.sleep(5.0)
    
    def disconnect(self):
        if self.connected: mt5.shutdown()

# ==================== WebSocketハンドラー ====================
async def websocket_handler(websocket):
    broker.add_client(websocket)
    try:
        # 初回挨拶は即時送信でOK（またはキューに入れても良い）
        await websocket.send(json.dumps({"type":"chat","text":"[happy] システム接続完了"}, ensure_ascii=False))
        
        async for message in websocket:
            try:
                data = json.loads(message)
                # ★修正: ニューススクリプトから受け取ったメッセージもキューに入れる
                if data.get("type") == "chat":
                    text = data.get("text", "")
                    logger.info(f"📨 ニュース受信: {text[:20]}... (キューに追加)")
                    await speech_queue.put(data)
            except: pass
    except: pass
    finally: broker.remove_client(websocket)

async def dashboard_websocket_handler(websocket):
    broker.add_client(websocket, is_dashboard=True)
    try:
        await websocket.send(json.dumps({
            "type": "init",
            "config": {"update_interval": config.update_interval}, # 簡略化
            "status": monitor.get_status()
        }, ensure_ascii=False))
        async for message in websocket: pass
    except: pass
    finally: broker.remove_client(websocket, is_dashboard=True)

async def websocket_router(websocket):
    path = getattr(websocket, 'path', '/')
    if path in ["/", "/direct-speech", "/direct"]: await websocket_handler(websocket)
    else: await websocket.close()

# ==================== メイン処理 ====================
async def main():
    print("MT5 & News 統合サーバー (キュー機能付き)")
    load_config_from_file() # 既存の設定読み込み関数があれば使用
    
    client = MT5Client()
    if not client.connect(): return
    
    # サーバーとワーカーとMT5監視を並列実行
    await asyncio.gather(
        websockets.serve(websocket_router, config.ws_host, config.ws_port),
        websockets.serve(dashboard_websocket_handler, config.ws_host, config.ws_port + 1),
        client.start_monitoring(),
        speech_worker() # ★ここが重要：キューを処理する係員を起動
    )

def load_config_from_file():
    # 簡易版の実装（必要なら既存のコードからコピーしてください）
    pass

if __name__ == '__main__':
    try: asyncio.run(main())
    except KeyboardInterrupt: print("停止")
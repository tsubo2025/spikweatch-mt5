# MT5 Price-Change Notifier for AItuber Kit

MetaTrader 5 (MT5) に接続し、指定した通貨ペアの価格変動をリアルタイムで監視する Python スクリプトです。
価格が設定した閾値（pips）を超えて変動すると、WebSocket を通じて JSON 形式のメッセージをブロードキャストします。

このシステムは、[AItuber Kit](https://github.com/tegnike/AItuber-Kit) のようなアプリケーションと連携し、為替市場の動きに応じて AI キャラクターがリアルタイムで反応する、といった用途を想定して設計されています。

## ✨ 主な機能

- **リアルタイム価格監視**: MetaTrader 5 と直接連携し、最新のティック価格を取得します。
- **複数通貨ペア対応**: 監視したい通貨ペアを簡単に追加・変更できます。
- **pips ベースの変動通知**: 小・中・大の 3 段階で変動閾値（pips）を設定し、変動レベルに応じたメッセージを送信します。
- **WebSocket サーバー内蔵**: 複数のクライアント（AItuber Kit など）が同時に接続し、価格変動の通知を受け取ることができます。
- **柔軟なメッセージ形式**: 通知メッセージには、テキスト、感情、役割などが含まれており、AI キャラクターのリアクション制御に最適です。

## ⚙️ 動作要件

- Python 3.7 以上
- [MetaTrader 5](https://www.metatrader5.com/) デスクトップアプリケーション
  - MT5 が PC にインストールされ、実行中である必要があります。
  - デモ口座またはリアル口座にログインしている必要があります。
- Python ライブラリ (依存関係)
  - `MetaTrader5`
  - `websockets`

## 📦 インストール

1.  プロジェクトをクローンまたはダウンロードします。

2.  必要な Python ライブラリをインストールします。
    ```bash
    pip install MetaTrader5 websockets
    ```

## 🔧 設定

スクリプト `mt5_monitor.py` の冒頭にある `設定` セクションを編集することで、動作をカスタマイズできます。

```python
# ==================== 設定 (Config) ====================
@dataclass
class Config:
    """アプリケーションの設定を管理するクラス"""
    # 監視する通貨ペア（MT5のシンボル名）と小数点以下の桁数
    watch_symbols: Dict[str, Dict[str, int]] = field(default_factory=lambda: {
        "USDJPY": {"digits": 3},
        "EURUSD": {"digits": 5},
        "GBPUSD": {"digits": 5},
        "EURJPY": {"digits": 3},
        "GBPJPY": {"digits": 3},
    })
    # 更新間隔（秒）
    update_interval: float = 1.0
    # 変動閾値（pips）
    small_threshold: float = 5.0
    medium_threshold: float = 16.0
    large_threshold: float = 30.0
    # メッセージ
    msg_small: str = "📊 すこしのうごきがありましたです"
    msg_medium: str = "⚠️ ちゅうくらいのうごきがありましたです"
    msg_large: str = "🚨 えええっ～びっくりです。大変です。"
    # WebSocketサーバー設定
    ws_host: str = "0.0.0.0"
    ws_port: int = 8000

config = Config()
```

- `watch_symbols`: 監視する通貨ペアとその桁数（`digits`）を指定します。`digits`は pips 計算に用いられます（例: JPY ペアは 3、EURUSD などは 5）。
- `update_interval`: MT5 へ価格を問い合わせる間隔（秒）です。
- `*_threshold`: `small`, `medium`, `large` の変動を検知する pips 数を設定します。
- `msg_*`: 各変動レベルで送信されるメッセージのテンプレートです。
- `ws_host`, `ws_port`: WebSocket サーバーが待機するホストとポートです。`0.0.0.0` を指定すると、ローカルネットワーク内の他の PC からもアクセス可能になります。

## 🚀 実行方法

1.  **MetaTrader 5 を起動**: PC で MT5 アプリケーションを起動し、口座にログインしておきます。

2.  **スクリプトを実行**: ターミナルまたはコマンドプロンプトで以下のコマンドを実行します。

    ```bash
    python mt5_monitor.py
    ```

3.  **クライアントから接続**: WebSocket クライアント（AItuber Kit など）から `ws://localhost:8000` （ホスト名を変更した場合はそのアドレス）に接続します。

## 🔌 WebSocket API

このサーバーは、価格が設定した閾値を超えて変動した際に、以下の形式の JSON メッセージを接続中の全クライアントに送信します。

### メッセージ形式

```json
{
  "text": "USDJPY が 5.1 pips 上昇 しました\n📊 すこしのうごきがありましたです",
  "role": "assistant",
  "emotion": "happy",
  "type": "message"
}
```

### フィールド説明

- `text`: 表示されるメッセージテキスト（通貨ペア名、変動量、方向、設定されたメッセージを含む）
- `role`: メッセージの役割（常に "assistant"）
- `emotion`: AI キャラクターの感情表現（"happy", "surprised", "concerned" など）
- `type`: メッセージタイプ（常に "message"）

## 📡 データの受け渡し方式

### 1. データフロー概要

```
MT5 → Python Script → WebSocket Server → AItuber Kit (Client)
```

1. **MT5 からのデータ取得**: MetaTrader5 Python API を使用してリアルタイムの価格データを取得
2. **価格変動の監視**: 前回の価格と比較し、設定した閾値（pips）を超える変動を検知
3. **WebSocket での配信**: 変動検知時に JSON 形式のメッセージを全接続クライアントにブロードキャスト

### 2. 通信プロトコル

- **プロトコル**: WebSocket (RFC 6455)
- **データ形式**: JSON
- **文字エンコーディング**: UTF-8
- **接続方式**: 永続接続（Keep-Alive）

### 3. 接続フロー

1. **クライアント接続**: `ws://localhost:8000` に WebSocket 接続を確立
2. **接続確認**: サーバーが接続を受け入れ、クライアントリストに追加
3. **データ受信待機**: クライアントは価格変動メッセージの受信を待機
4. **メッセージ受信**: 価格変動検知時に JSON メッセージを受信
5. **接続終了**: クライアントまたはサーバーが接続を切断

### 4. エラーハンドリング

- **接続エラー**: クライアント接続失敗時は自動的にリトライ
- **データ送信エラー**: 切断されたクライアントは自動的にリストから除去
- **MT5 接続エラー**: MT5 との接続が失われた場合はエラーログを出力し、再接続を試行

### 5. パフォーマンス特性

- **レイテンシ**: 価格変動検知から配信まで通常 1 秒以内
- **スループット**: 複数クライアント同時接続対応
- **リソース使用量**: CPU 使用率は通常 1-3%、メモリ使用量は約 10-20MB

---

**免責事項**: 本ソフトウェアは情報提供を目的としており、投資助言を構成するものではありません。本ソフトウェアの使用によって生じたいかなる損害についても、開発者は一切の責任を負いません。

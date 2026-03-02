> [!WARNING]
> コスト計算の正確性は保証しません。参考程度です。<br>
> また、料金レートはライブラリ内のTOMLに保持しており、各サービスのアップデートなどでズレる可能性があります。

# LiteLLM Ledger

[LiteLLM](https://github.com/BerriAI/litellm) の `completion()` を薄くラップし、呼び出し履歴・コスト計算をローカルDBに記録するライブラリ。<br>
使用する際には`litellm_ledger/` ディレクトリを丸ごとコピーする。

## 機能

- `chat()` を呼んだタイミングで履歴とコストを SQLite に記録
- 料金レートは TOML ファイルで管理　※OpenAI APIとGemini APIのみ対応
- 日付・日付範囲で履歴・コスト・CSV を取得

## 動作要件

- Python 3.11 以上
- 依存パッケージ: `litellm`

```bash
pip install -r requirements.txt
```

## 使い方

```python
from litellm_ledger import LiteLLMClient

client = LiteLLMClient(
    db_path="ledger_history.db",
    api_keys={"GEMINI_API_KEY": "your-api-key"},
)

# テキスト
response = client.chat(
    "gemini/gemini-2.5-flash",
    [{"role": "user", "content": "こんにちは"}],
)
print(response.choices[0].message.content)

# 画像（base64）
import base64
from pathlib import Path
image_b64 = base64.b64encode(Path("sample.jpg").read_bytes()).decode()
response = client.chat("gemini/gemini-2.5-flash", [
    {
        "role": "user",
        "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
            {"type": "text", "text": "何が写っていますか？"},
        ],
    }
])

# temperature や max_tokens の指定
response = client.chat(
    "gemini/gemini-2.5-flash",
    [{"role": "user", "content": "Hello"}],
    temperature=0.5,
    max_tokens=256,
)

# 履歴・コスト確認
print(client.db.get_all())
print(f"Total: ${client.db.get_total_cost():.6f} USD")

# CSV 出力
client.db.to_csv("ledger_history.csv")
```

## API

### `LiteLLMClient`

| 引数 | デフォルト | 説明 |
|---|---|---|
| `db_path` | `"ledger_history.db"` | SQLite DB ファイルのパス　※存在しない場合は生成 |
| `pricing_dir` | `litellm_ledger/pricing/` | 料金 TOML ディレクトリ |
| `api_keys` | `None` | `{"GEMINI_API_KEY": "..."}` `OPENAI_API_KEY` / `GEMINI_API_KEY`  |

| メソッド | 説明 |
|---|---|
| `chat(model, messages, **kwargs)` | LiteLLM を呼び出し、履歴とコストを記録して `ModelResponse` を返す |

### `HistoryDB`（`client.db`）

日付は `"YYYY-MM-DD"` 文字列または `datetime.date` オブジェクトで指定できる。

| メソッド | 説明 |
|---|---|
| `get_all()` | 全履歴を昇順で返す |
| `get_total_cost()` | 累計コスト（USD）を返す |
| `to_csv(path)` | 全履歴を CSV に出力する |
| `to_csv_string()` | 全履歴を CSV 文字列で返す |
| `get_by_date(date)` | 指定日付の履歴を返す |
| `get_cost_by_date(date)` | 指定日付のコスト合計を返す |
| `to_csv_by_date(path, date)` | 指定日付の履歴を CSV に出力する |
| `get_by_date_range(start, end)` | 指定範囲（両端含む）の履歴を返す |
| `get_cost_by_date_range(start, end)` | 指定範囲のコスト合計を返す |
| `to_csv_by_date_range(path, start, end)` | 指定範囲の履歴を CSV に出力する |

**CSV フォーマット:**

```
id, timestamp, model, input_tokens, output_tokens, thinking_tokens, total_tokens, cost_usd
```

- `output_tokens`: thinking/reasoning トークンを除いた純粋な出力トークン数
- `timestamp`: `YYYY-MM-DD HH:MM:SS`（ローカルタイムゾーン）

## 料金 TOML の管理

`litellm_ledger/pricing/` の `*.toml` を自動ロードする。<br>

```toml
[models."gemini/gemini-2.5-flash"]
input    = 0.30   # USD per 1M tokens
output   = 2.50
thinking = 2.50   # 省略可。省略時は output レートを使用

# 段階料金（省略可）
[models."gemini/gemini-2.5-pro".tier_over]
threshold = 200000
input     = 2.50
output    = 15.00
thinking  = 15.00
```

未登録モデルを使用した場合、コストは `0.0` として記録され警告が出力される。

```python
print(client.pricing.list_models())  # 登録済みモデル一覧
```

# Author
高橋かずひと(https://x.com/KzhtTkhs)
 
# License 
LiteLLM Ledger is under [MIT License](LICENSE).<br>
サンプル画像は[フリー素材ぱくたそ](https://www.pakutaso.com)様の写真を利用しています。

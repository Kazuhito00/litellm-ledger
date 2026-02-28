"""litellm_ledger の使い方の例（Gemini Flash: テキスト＋画像）."""

import base64
from pathlib import Path

from litellm_ledger import LiteLLMClient

MODEL = "gemini/gemini-2.5-flash"


def main():
    client = LiteLLMClient(
        db_path="ledger_history.db",
        api_keys={"GEMINI_API_KEY": "Set Your API KEY"},
    )

    # --- テキストチャット ---
    print(f"=== [{MODEL}] テキスト ===")
    response = client.chat(
        MODEL,
        [
            {
                "role": "user",
                "content": "Pythonで'Hello, World!'を出力するコードを1行で書いて",
            }
        ],
    )
    print(response.choices[0].message.content)
    print(f"コスト: ${client.db.get_all()[-1]['cost_usd']:.6f}")
    print()

    # --- 画像入力 ---
    image_bytes = (Path(__file__).parent / "sample.jpg").read_bytes()
    b64 = base64.b64encode(image_bytes).decode()
    vision_messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                },
                {
                    "type": "text",
                    "text": "この画像に何が写っていますか？詳しく説明してください。",
                },
            ],
        }
    ]

    print(f"=== [{MODEL}] 画像 ===")
    response = client.chat(MODEL, vision_messages)
    print(response.choices[0].message.content)
    print(f"コスト: ${client.db.get_all()[-1]['cost_usd']:.6f}")
    print()

    # --- サマリー ---
    print("=== サマリー ===")
    history = client.db.get_all()
    print(f"総呼出し回数:       {len(history)}")
    print(f"総入力トークン:     {sum(r['input_tokens'] for r in history):,}")
    print(f"総出力トークン:     {sum(r['output_tokens'] for r in history):,}")
    print(f"総Thinkingトークン: {sum(r['thinking_tokens'] for r in history):,}")
    print(f"総コスト:           ${client.db.get_total_cost():.6f}")

    client.db.to_csv("sample_cost_log.csv")


if __name__ == "__main__":
    main()

import os
from pathlib import Path

import litellm

from .history import CallRecord, HistoryDB
from .pricing import PricingManager


class LiteLLMClient:
    """
    litellm.completion を薄くラップし、呼び出し履歴とコストを自動記録するクライアント。

    Usage:
        client = LiteLLMClient(
            api_keys={"OPENAI_API_KEY": "sk-...", "GEMINI_API_KEY": "..."}
        )
        response = client.chat("gpt-4o", [{"role": "user", "content": "Hello"}])
        client.db.to_csv("history.csv")
        print(f"Total: ${client.db.get_total_cost():.6f} USD")
    """

    def __init__(
        self,
        db_path: str | Path = "history.db",
        pricing_dir: str | Path | None = None,
        api_keys: dict[str, str] | None = None,
    ):
        """
        Args:
            db_path: SQLite DB ファイルのパス。自動作成される。
            pricing_dir: pricing TOML ディレクトリのパス。
                         None の場合は litellm_ledger/pricing/ を使用する。
            api_keys: APIキーの辞書。キーは環境変数名（例: "OPENAI_API_KEY"）。
                      値が空文字の場合は設定しない。
        """
        if api_keys:
            for env_var, value in api_keys.items():
                if value:
                    os.environ[env_var] = value
        self.db = HistoryDB(db_path)
        self.pricing = PricingManager(pricing_dir)

    def chat(
        self,
        model: str,
        messages: list[dict],
        **kwargs,
    ) -> litellm.ModelResponse:
        """
        litellm.completion を呼び出し、レスポンスを記録して返す。
        litellm の追加オプション（temperature, max_tokens 等）は **kwargs で透過的に渡せる。
        """
        response = litellm.completion(model=model, messages=messages, **kwargs)
        self._record(model, response)
        return response

    def _record(self, model: str, response: litellm.ModelResponse) -> None:
        usage = response.usage
        input_tokens   = getattr(usage, "prompt_tokens", 0) or 0
        completion_tokens = getattr(usage, "completion_tokens", 0) or 0
        total_tokens   = getattr(usage, "total_tokens", 0) or 0
        thinking_tokens = self._extract_thinking_tokens(usage)

        # LiteLLM は Gemini・OpenAI ともに completion_tokens に thinking/reasoning を
        # 含めて返す（Gemini は is_candidate_token_count_inclusive で正規化済み）。
        # Usage.__init__ が completion_tokens_details.text_tokens を自動計算するので
        # それを優先使用し、なければ手動で引いて純粋な出力トークンを得る。
        details = getattr(usage, "completion_tokens_details", None)
        text_tokens = getattr(details, "text_tokens", None) if details else None
        output_tokens = text_tokens if text_tokens is not None else max(0, completion_tokens - thinking_tokens)

        cost = self.pricing.calculate_cost(
            model, input_tokens, output_tokens, thinking_tokens
        )
        self.db.save(CallRecord(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            thinking_tokens=thinking_tokens,
            total_tokens=total_tokens,
            cost_usd=cost,
        ))

    @staticmethod
    def _extract_thinking_tokens(usage) -> int:
        """
        複数プロバイダの thinking/reasoning トークン数を統一的に取り出す。

        Gemini の生フィールド `thoughtsTokenCount` は LiteLLM が
        `completion_tokens_details.reasoning_tokens` に変換して格納する
        （usage.thoughts_tokens という直接フィールドは存在しない）。

        優先順位:
          1. usage.completion_tokens_details.reasoning_tokens
             - OpenAI: API がそのまま返す reasoning_tokens
             - Gemini: thoughtsTokenCount → reasoning_tokens に変換済み
          2. usage.reasoning_tokens  (LiteLLM フォールバックフィールド)
          3. 0
        """
        details = getattr(usage, "completion_tokens_details", None)
        if details is not None:
            val = getattr(details, "reasoning_tokens", None)
            if val:
                return int(val)

        val = getattr(usage, "reasoning_tokens", None)
        if val:
            return int(val)

        return 0

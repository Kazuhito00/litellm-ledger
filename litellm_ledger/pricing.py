import tomllib
from pathlib import Path


class PricingManager:
    """
    pricing/ ディレクトリ以下の全 *.toml を自動ロードしてモデル料金を管理する。
    新サービスの TOML ファイルを追加するだけで自動認識される。

    TOML フォーマット:
        [models."model-name"]
        input    = 2.50   # USD per 1M tokens
        output   = 10.00  # USD per 1M tokens
        thinking = 10.00  # USD per 1M tokens (省略可。省略時は output レートを使用)

        # 段階料金（省略可）: input_tokens が threshold を超えた場合に適用
        [models."model-name".tier_over]
        threshold = 200000
        input     = 2.50
        output    = 15.00
        thinking  = 15.00
    """

    def __init__(self, pricing_dir: str | Path | None = None):
        if pricing_dir is None:
            pricing_dir = Path(__file__).parent / "pricing"
        self._rates: dict[str, dict] = {}
        self._load_all(Path(pricing_dir))

    def _load_all(self, pricing_dir: Path) -> None:
        for toml_file in sorted(pricing_dir.glob("*.toml")):
            with open(toml_file, "rb") as f:
                data = tomllib.load(f)
            for model_name, rates in data.get("models", {}).items():
                self._rates[model_name] = rates

    def calculate_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        thinking_tokens: int = 0,
    ) -> float:
        """
        コストを USD で返す。モデルが未登録の場合は 0.0 を返す。
        thinking_tokens は専用レートがあればそちらを、なければ output レートで計算する。
        """
        rates = self._rates.get(model)
        if rates is None:
            print(f"[litellm_ledger] pricing not found for model '{model}', cost set to 0.0")
            return 0.0

        # 段階料金: input_tokens が threshold を超えた場合は tier_over レートを使用
        tier_over = rates.get("tier_over")
        if tier_over and input_tokens > tier_over["threshold"]:
            rates = {**rates, **tier_over}

        M = 1_000_000
        cost = (
            input_tokens * rates["input"] / M
            + output_tokens * rates["output"] / M
        )
        if thinking_tokens > 0:
            thinking_rate = rates.get("thinking", rates["output"])
            cost += thinking_tokens * thinking_rate / M

        return round(cost, 8)

    def list_models(self) -> list[str]:
        """登録済みモデル名の一覧を返す。"""
        return list(self._rates.keys())

    def get_rates(self, model: str) -> dict | None:
        """指定モデルのレートを返す。未登録なら None。"""
        return self._rates.get(model)

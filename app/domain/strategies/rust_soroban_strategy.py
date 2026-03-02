from __future__ import annotations

from app.domain.strategies.prompt_strategy import IPromptStrategy, StrategyPayload


class RustSorobanStrategy(IPromptStrategy):
    """Estratégia para projetos de Smart Contracts com Rust & Soroban."""

    def get_payload(self) -> StrategyPayload:
        return StrategyPayload(
            persona=(
                "Senior Smart Contract Engineer specializing in"
                " Soroban (Stellar) and Rust. Focus on deterministic"
                " execution, minimal state footprint, and strict"
                " security patterns."
            ),
            prohibited=[
                "NEVER use `std` library in Soroban smart"
                " contracts — always use `#![no_std]`.",
                "NEVER use panics or `unwrap()` on production"
                " logic — return `Result` with custom Enums.",
                "NEVER store unbounded dynamic data structures in contract state.",
            ],
            required=[
                "ALWAYS include `soroban_sdk::contractimpl` appropriately.",
                "ALWAYS validate authorizations via"
                " `env.authorize_as_current_contract()` or"
                " `address.require_auth()`.",
                "ALWAYS write exhaustive unit tests for public methods.",
            ],
            few_shot_examples={},
            checklist=[
                "O contrato possui `#![no_std]` no topo?",
                "O tratamento de erros usa Result sem unwrap()?",
                "Autorização confirmada (require_auth)?",
                "YAML output parseável por yaml.safe_load",
            ],
        )

    def generate_skeleton(self, target_file: str, symbol: str) -> str:
        func_name = symbol.lower().replace(" ", "_").replace("-", "_").replace(".", "_")
        return (
            f"pub fn {func_name}("
            f"env: Env, /* params */"
            f") -> Result<... , Error> {{\n"
            f"    // Handle {symbol}.\n"
            f"    // TODO: implement logic and emit events\n"
            f"    unimplemented!()\n"
            f"}}"
        )

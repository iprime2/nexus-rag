# ADR-0007: Native LLM provider abstraction

- **Status:** Accepted (2026-11-20)
- **Date:** 2026-11-20

## Context
The platform must support OpenAI, Anthropic and AWS Bedrock without coupling to any one of them, with streaming, structured output and token accounting. Providers differ in real ways: parameter support (e.g. current Claude models reject sampling parameters such as `temperature`), structured-output mechanisms, streaming event shapes, and citation features.

## Decision
- A small `LLMProvider` protocol (`generate`, `stream` → normalized events `TextDelta | UsageReport | Completed | ProviderError`) with explicit `ProviderCapabilities`.
- One adapter per provider using the vendor's **official SDK** (`openai`, `anthropic`, `boto3` Bedrock Runtime Converse API).
- The same pattern for `EmbeddingProvider` and `Reranker`.
- Models are configuration: a per-provider allow-list and per-provider defaults set in `.env`.
- LangChain is not used for these layers. It may be used for isolated utilities (e.g. text splitters) if it saves real code.

## Alternatives considered
| Option | Pros | Cons |
|---|---|---|
| **Native adapters** | Full control, readable stack traces, new provider features available immediately, easy to type-check | ~3 small adapters to write and maintain |
| LangChain chat models | Many providers out of the box | Abstraction layers obscure errors; lags provider features; the lowest-common-denominator interface hides capability differences |
| LiteLLM | One OpenAI-shaped API for everything | Another dependency in the hot path; provider-specific features flattened |

## Consequences
- Adding a provider (e.g. a vLLM OpenAI-compatible endpoint) means writing one adapter plus contract tests.
- Contract tests run every adapter against the same scenarios (streaming order, usage reporting, error mapping).

"""
AI-сервис для Flowoi (см. project_flowoi_ai_architecture).

Архитектура:
- VPS в РФ → Anthropic заблокирован → AI_PROXY_URL (Render вне РФ)
- function calling — LLM запрашивает наши данные через tools
- история чатов в БД (AIChat, AIMessage)
- usage tracking (AIUsageMonthly)
"""

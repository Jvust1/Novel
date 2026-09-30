# tiktoken context budgeting — 2026-09-30

Upstream: `openai/tiktoken`  
Revision inspected: `4e71bbe0c078468e00fefbf94b39849389f346e5`  
License: MIT

Novel's ContextAssembler can now accept a TokenCounter and token budgets for Canon and Recall. If tiktoken is unavailable, the counter falls back to a deterministic character-per-token estimate, and the original character budgets remain the default unless token budgets are explicitly configured.

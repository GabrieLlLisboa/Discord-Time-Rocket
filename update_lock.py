import asyncio

# trava compartilhada entre console.py (comando "update" manual) e
# auto_update.py (checagem automática a cada X segundos), pra garantir que
# nunca rolem dois "git pull" ao mesmo tempo na mesma pasta — se isso
# acontece, um processo pisa no outro no meio do pull e o git aborta com
# erro de "local changes would be overwritten by merge"
LOCK = asyncio.Lock()

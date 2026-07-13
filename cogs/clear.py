from discord.ext import commands

# ─────────────────────────────────────────────
#  Cog: Limpar mensagens
#  Arquivo: cogs/clear.py
#  Comandos: !clear all | !clear <número>
# ─────────────────────────────────────────────

class Clear(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="clear")
    @commands.has_permissions(administrator=True)
    async def clear(self, ctx: commands.Context, quantidade: str = None):
        """
        Limpa mensagens do canal.
        Uso:
          !clear all    → apaga todas as mensagens (até 1000)
          !clear 50     → apaga as últimas 50 mensagens
        """
        await ctx.message.delete()

        if quantidade is None:
            await ctx.send(
                "⚠️ Use `!clear all` ou `!clear <número>` (ex: `!clear 50`)",
                delete_after=5
            )
            return

        # ── !clear all ─────────────────────────────────────────────────────────
        if quantidade.lower() == "all":
            deletadas = 0
            while True:
                # purge apaga no máximo 100 por vez (limite do Discord)
                apagadas = await ctx.channel.purge(limit=100)
                deletadas += len(apagadas)
                if len(apagadas) < 100:
                    break

            confirmacao = await ctx.send(f"🗑️ **{deletadas}** mensagens apagadas.")
            await confirmacao.delete(delay=4)
            print(f"[CLEAR] ✅ {deletadas} mensagens apagadas em #{ctx.channel.name} por {ctx.author}.")
            return

        # ── !clear <número> ────────────────────────────────────────────────────
        try:
            numero = int(quantidade)
        except ValueError:
            await ctx.send(
                "❌ Valor inválido. Use `!clear all` ou `!clear <número>`.",
                delete_after=5
            )
            return

        if numero < 1 or numero > 1000:
            await ctx.send(
                "❌ O número deve ser entre **1** e **1000**.",
                delete_after=5
            )
            return

        deletadas = await ctx.channel.purge(limit=numero)
        confirmacao = await ctx.send(f"🗑️ **{len(deletadas)}** mensagens apagadas.")
        await confirmacao.delete(delay=4)
        print(f"[CLEAR] ✅ {len(deletadas)} mensagens apagadas em #{ctx.channel.name} por {ctx.author}.")

    @clear.error
    async def clear_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ Você precisa ser **Administrador** para usar este comando.", delete_after=5)


async def setup(bot: commands.Bot):
    await bot.add_cog(Clear(bot))

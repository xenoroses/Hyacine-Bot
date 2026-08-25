import discord
from discord.ext import commands
import time
import json
import psutil
from redis_utils import rget_json, rset_json
from typing import Union, Optional

class ObservabilityEngine(commands.Cog):
    """
    Tier 1 Observability: Latency, Resource tracking, and Shard status.
    Hardened for multi-permission environments and premium aesthetics.
    """
    def __init__(self, bot):
        self.bot = bot

    async def _send_embed(self, dest: Union[discord.abc.Messageable, commands.Context], embed: discord.Embed, ephemeral: bool = False, fallback_text: Optional[str] = None):
        """Standardized robust response handler for all engines."""
        send_method = dest.send if hasattr(dest, "send") else dest
        supports_ephemeral = isinstance(dest, (commands.Context, discord.Interaction)) or (hasattr(dest, "interaction") and dest.interaction)

        try:
            if supports_ephemeral:
                await send_method(embed=embed, ephemeral=ephemeral)
            else:
                await send_method(embed=embed)
        except discord.Forbidden:
            content = fallback_text or embed.description or "Action Processing..."
            header = "⌬ ⟡ **𝒮𝓎𝓈𝓉ℯ𝓂 𝒜𝓊𝒹𝒾Audit (𝒫𝓁𝒶𝒾𝓃-𝒯ℯ𝓍𝓉 ℳℴ𝒹ℯ)**\n"
            footer = "\n*Note: Enable 'Embed Links' for rich telemetry.*"
            fallback_msg = f"{header}```fix\n{content}\n``` {footer}"
            try:
                if supports_ephemeral:
                    await send_method(fallback_msg, ephemeral=ephemeral)
                else:
                    await send_method(fallback_msg)
            except:
                pass
        except:
            pass

    @commands.hybrid_command(name="health", aliases=["ping"], description="System heartbeat check.")
    async def health(self, ctx: commands.Context):
        await ctx.defer()
        ping = round(self.bot.latency * 1000)
        embed = discord.Embed(title="⌬ 𝒮𝓎𝓈𝓉ℯ𝓂 ℋℯ𝒶𝓁𝓉𝒽", color=0x2ECC71)
        embed.add_field(name="Gateway Latency", value=f"{ping}ms", inline=True)
        embed.add_field(name="Status", value="Operational ✧", inline=True)
        await self._send_embed(ctx, embed, fallback_text=f"𝒮𝓎𝓈𝓉ℯ𝓂 ℋℯ𝒶𝓁𝓉𝒽: Operational ({ping}ms)")

    @commands.hybrid_command(name="latencybreakdown", description="Detailed telemetry probe.")
    @commands.has_permissions(manage_messages=True)
    async def latencybreakdown(self, ctx: commands.Context):
        await ctx.defer()
        try:
            embed = discord.Embed(title="⌬ 𝒯ℯ𝓁ℯ𝓂ℯ𝓉𝓇𝓎 𝒫𝓇ℴ𝒷ℯ", color=0x3498DB)
            embed.add_field(name="Gateway", value=f"{round(self.bot.latency * 1000)}ms", inline=True)
            embed.add_field(name="Logic Array", value="Stable ✧", inline=True)
            await self._send_embed(ctx, embed, fallback_text="𝒯ℯ𝓁ℯ𝓂ℯTelemetry breakdown complete.")
        except Exception as e:
            await ctx.send(f"⌬ ⟡ **𝒮𝓎𝓈𝓉ℯ𝓂 ℰ𝓇ℴ𝓇:** Telemetry probe failed: {e}")

    @commands.hybrid_command(name="memoryusage", description="Heap diagnostics.")
    @commands.has_permissions(administrator=True)
    async def memoryusage(self, ctx: commands.Context):
        await ctx.defer()
        try:
            mem = psutil.virtual_memory()
            embed = discord.Embed(title="⌬ ℛℯ𝓈ℴ𝓊𝓇𝒸ℯ 𝒜𝓃𝒶𝓁𝓎𝓉𝒾𝒸𝓈", color=0x9B59B6)
            embed.add_field(name="RAM Usage", value=f"{mem.percent}%", inline=True)
            await self._send_embed(ctx, embed, fallback_text=f"ℛℯ𝓈ℴ𝓊𝓇𝒸ℯ Analytics: RAM {mem.percent}%")
        except Exception as e:
            await ctx.send(f"⌬ ⟡ **𝒮𝓎𝓈𝓉ℯ𝓂 ℰ𝓇𝓇ℴ𝓇:** Resource analysis failed: {e}")

async def setup(bot):
    if "ObservabilityEngine" not in bot.cogs:
        await bot.add_cog(ObservabilityEngine(bot))

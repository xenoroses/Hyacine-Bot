import asyncio
import json
from collections import defaultdict
from discord.ext import commands, tasks
from discord import app_commands
import discord
from redis_utils import rget_json, rset_json, rdelete
from typing import Union, Optional

async def safe_respond(interaction: discord.Interaction, embed: Optional[discord.Embed] = None, content: Optional[str] = None, ephemeral: bool = True):
    """Fail-safe interaction response handler that guarantees exactly one message response."""
    try:
        if not interaction.response.is_done():
            if embed and content:
                await interaction.response.send_message(content=content, embed=embed, ephemeral=ephemeral)
            elif embed:
                await interaction.response.send_message(embed=embed, ephemeral=ephemeral)
            else:
                await interaction.response.send_message(content=content, ephemeral=ephemeral)
        else:
            if embed and content:
                await interaction.followup.send(content=content, embed=embed, ephemeral=ephemeral)
            elif embed:
                await interaction.followup.send(embed=embed, ephemeral=ephemeral)
            else:
                await interaction.followup.send(content=content, ephemeral=ephemeral)
    except Exception:
        pass


class HyacineStickyModal(discord.ui.Modal, title="Set Sticky Notice"):
    def __init__(self, target_channel: discord.TextChannel):
        super().__init__()
        self.target_channel = target_channel

        self.message_input = discord.ui.TextInput(
            label="Sticky Message Content",
            style=discord.TextStyle.paragraph,
            placeholder="Type your multiline sticky message here...\nUse # Title, ## Header, **bold**, or > quotes.",
            required=True,
            max_length=2000
        )
        self.add_item(self.message_input)

        self.embed_input = discord.ui.TextInput(
            label="Format as Rich Embed? (yes/no)",
            style=discord.TextStyle.short,
            placeholder="Type 'yes' to send inside a sleek embed, or 'no' for plain text.",
            required=False,
            default="no",
            max_length=5
        )
        self.add_item(self.embed_input)

    async def on_submit(self, interaction: discord.Interaction):
        message_text = self.message_input.value.strip()
        as_embed = self.embed_input.value.strip().lower() in ("yes", "y", "true", "1")
        key = f"sticky:{self.target_channel.id}"

        # Immediately post the initial sticky message into the target channel
        sent_msg_id = None
        try:
            if as_embed:
                embed_sticky = discord.Embed(description=message_text, color=0xFF69B4)
                new_msg = await self.target_channel.send(embed=embed_sticky)
            else:
                new_msg = await self.target_channel.send(message_text)
            sent_msg_id = new_msg.id
        except Exception:
            pass

        await rset_json(interaction.client, key, {
            "message": message_text,
            "is_embed": as_embed,
            "last_id": sent_msg_id
        })

        format_type = "Rich Embed" if as_embed else "Plain Text / Markdown"
        confirm_embed = discord.Embed(
            title="📌 Sticky Message Configured",
            description=(
                f"Sticky notice successfully posted and active in {self.target_channel.mention}!\n\n"
                f"• **Format:** `{format_type}`\n"
                f"• **Content Preview:**\n>>> {message_text[:200]}" + ("..." if len(message_text) > 200 else "")
            ),
            color=0xFF69B4
        )
        await safe_respond(interaction, embed=confirm_embed, ephemeral=True)


class StickyCommands(commands.Cog):
    """
    Premium Sticky Message Engine.
    Ensures persistent visibility of channel notices with full multiline, Markdown, and Rich Embed support.
    """
    sticky_group = app_commands.Group(name="sticky", description="Sticky message engine administrator controls.")

    def __init__(self, bot):
        self.bot = bot
        self.channel_locks = defaultdict(asyncio.Lock)
        self.prune_trackers.start()

    def cog_unload(self):
        self.prune_trackers.cancel()

    @tasks.loop(hours=24)
    async def prune_trackers(self):
        for cid in list(self.channel_locks.keys()):
            if not self.bot.get_channel(cid):
                del self.channel_locks[cid]

    async def _send_sticky_msg(self, channel: discord.TextChannel, sticky_text: str, is_embed: bool) -> discord.Message:
        """Post sticky notice formatted as Rich Embed or formatted Markdown text."""
        if is_embed:
            embed = discord.Embed(
                description=sticky_text,
                color=0xFF69B4
            )
            return await channel.send(embed=embed)
        return await channel.send(sticky_text)

    async def _purge_sticky_data(self, channel: discord.TextChannel) -> bool:
        """Purge sticky from store AND delete old message from channel history."""
        key = f"sticky:{channel.id}"
        data = await rget_json(self.bot, key)
        deleted = False

        if data:
            deleted = True
            last_id = data.get("last_id")
            await rdelete(self.bot, key)
            if last_id:
                try:
                    old_msg = await channel.fetch_message(last_id)
                    await old_msg.delete()
                except: pass
        else:
            await rdelete(self.bot, key)

        # Fallback sweep: remove any orphaned bot messages in channel history
        try:
            async for msg in channel.history(limit=15):
                if msg.author.id == self.bot.user.id:
                    # Ignore command confirmations or system embeds
                    if msg.embeds and any(kw in (msg.embeds[0].title or "") for kw in ["Configured", "Removed", "Protocol", "Audit"]):
                        continue
                    if "protocol engaged" in msg.content.lower():
                        continue
                    try:
                        await msg.delete()
                        deleted = True
                        break
                    except: pass
        except: pass

        return deleted

    # --- Slash Commands Group ---

    @sticky_group.command(name="modal", description="Open multiline paragraph modal popup to set sticky notice with newlines & headers.")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def sticky_modal_slash(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        target_ch = channel or interaction.channel
        modal = HyacineStickyModal(target_channel=target_ch)
        await interaction.response.send_modal(modal)

    @sticky_group.command(name="set", description="Set sticky notice message for this channel.")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def sticky_set_slash(
        self,
        interaction: discord.Interaction,
        message: str,
        channel: Optional[discord.TextChannel] = None,
        as_embed: bool = False
    ):
        target_ch = channel or interaction.channel
        key = f"sticky:{target_ch.id}"

        async with self.channel_locks[target_ch.id]:
            # Sweep channel history for previous sticky messages
            try:
                async for past_msg in target_ch.history(limit=15):
                    if past_msg.author.id == self.bot.user.id:
                        if past_msg.embeds and any(kw in (past_msg.embeds[0].title or "") for kw in ["Configured", "Removed", "Portal"]):
                            continue
                        try:
                            await past_msg.delete()
                        except: pass
            except: pass

            # Post initial message
            sent_msg_id = None
            try:
                msg = await self._send_sticky_msg(target_ch, message, as_embed)
                sent_msg_id = msg.id
            except: pass

            await rset_json(self.bot, key, {
                "message": message,
                "is_embed": as_embed,
                "last_id": sent_msg_id
            })

        format_type = "Rich Embed" if as_embed else "Plain Text / Markdown"
        embed = discord.Embed(
            title="📌 Sticky Message Configured",
            description=(
                f"Sticky notice successfully set for {target_ch.mention}!\n\n"
                f"• **Format:** `{format_type}`\n"
                f"• **Content Preview:**\n>>> {message}"
            ),
            color=0xFF69B4
        )
        await safe_respond(interaction, embed=embed, ephemeral=True)

    @sticky_group.command(name="remove", description="Remove sticky message from a channel.")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def sticky_remove_slash(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        target_ch = channel or interaction.channel

        async with self.channel_locks[target_ch.id]:
            removed = await self._purge_sticky_data(target_ch)

        if removed:
            await safe_respond(interaction, content=f"🗑️ **Sticky message removed from {target_ch.mention}.**", ephemeral=True)
        else:
            await safe_respond(interaction, content=f"⚠️ No active sticky message found in {target_ch.mention}.", ephemeral=True)

    # --- Prefix Commands Fallback (!sticky / ,sticky / hya unsticky) ---

    @commands.command(name="sticky")
    async def sticky_prefix(self, ctx: commands.Context, *, message: str):
        """Prefix command fallback (!sticky <message> / !sticky -embed <message> / ,sticky <message>)."""
        if not ctx.author.guild_permissions.manage_channels and not ctx.author.guild_permissions.administrator:
            return await ctx.send("❌ You need **Manage Channels** or **Administrator** permission.")

        is_embed = False
        clean_msg = message.strip()

        if clean_msg.startswith("-embed "):
            is_embed = True
            clean_msg = clean_msg[7:].strip()
        elif clean_msg.startswith("--embed "):
            is_embed = True
            clean_msg = clean_msg[8:].strip()
        elif clean_msg.startswith("embed "):
            is_embed = True
            clean_msg = clean_msg[6:].strip()

        key = f"sticky:{ctx.channel.id}"
        async with self.channel_locks[ctx.channel.id]:
            # Delete author command message
            try:
                await ctx.message.delete()
            except: pass

            # Sweep channel history to remove any existing bot sticky messages
            try:
                async for past_msg in ctx.channel.history(limit=15):
                    if past_msg.author.id == self.bot.user.id:
                        if past_msg.embeds and any(kw in (past_msg.embeds[0].title or "") for kw in ["Configured", "Removed", "Portal"]):
                            continue
                        try:
                            await past_msg.delete()
                        except: pass
            except: pass

            # Post single sticky message at the bottom
            sent_msg_id = None
            try:
                msg = await self._send_sticky_msg(ctx.channel, clean_msg, is_embed)
                sent_msg_id = msg.id
            except: pass

            await rset_json(self.bot, key, {
                "message": clean_msg,
                "is_embed": is_embed,
                "last_id": sent_msg_id
            })

    @commands.command(name="unsticky")
    async def unsticky_prefix(self, ctx: commands.Context):
        """Prefix command fallback (!unsticky / ,unsticky / hya unsticky)."""
        if not ctx.author.guild_permissions.manage_channels and not ctx.author.guild_permissions.administrator:
            return await ctx.send("❌ You need **Manage Channels** or **Administrator** permission.")

        async with self.channel_locks[ctx.channel.id]:
            removed = await self._purge_sticky_data(ctx.channel)

        if removed:
            await ctx.send("⌬ Sticky message removed from this channel.")
        else:
            await ctx.send("⚠️ No active sticky message found in this channel.")

    # --- Event Listener ---

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild: return

        content_lower = message.content.lower().strip()
        if "unsticky" in content_lower or "sticky" in content_lower:
            return

        key = f"sticky:{message.channel.id}"
        data = await rget_json(self.bot, key)
        if not data: return

        sticky_text = data.get("message")
        is_embed = data.get("is_embed", False)
        last_id = data.get("last_id")

        if not sticky_text: return
        if last_id and message.channel.last_message_id == int(last_id): return

        async with self.channel_locks[message.channel.id]:
            current_data = await rget_json(self.bot, key)
            if not current_data: return

            current_last_id = current_data.get("last_id")
            sticky_text = current_data.get("message")
            is_embed = current_data.get("is_embed", False)

            if not sticky_text: return

            # Re-check inside lock to eliminate race conditions
            if current_last_id and message.channel.last_message_id == int(current_last_id):
                return

            # Purge any existing bot sticky messages in recent channel history to guarantee 0 duplicates
            try:
                async for past_msg in message.channel.history(limit=15):
                    if past_msg.author.id == self.bot.user.id and past_msg.id != message.id:
                        if past_msg.embeds and any(kw in (past_msg.embeds[0].title or "") for kw in ["Configured", "Removed", "Portal"]):
                            continue
                        try:
                            await past_msg.delete()
                        except: pass
            except: pass

            try:
                new_msg = await self._send_sticky_msg(message.channel, sticky_text, is_embed)
                current_data["last_id"] = new_msg.id
                await rset_json(self.bot, key, current_data)
            except: pass

async def setup(bot):
    if "StickyCommands" not in bot.cogs:
        await bot.add_cog(StickyCommands(bot))

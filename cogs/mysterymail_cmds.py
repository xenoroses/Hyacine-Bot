import discord
from discord.ext import commands
from discord import app_commands
import uuid
import json
import os
from datetime import datetime, timezone
from typing import Union, Optional
from redis_utils import rget_json, rset_json, rdelete, rget, rset

HYACINE_BANNER_PATH = "assets/banner.png"
HYACINE_BANNER_CDN = "https://cdn.discordapp.com/attachments/1000000000000000000/banner_ce.png"

class MysteryMailModal(discord.ui.Modal, title="Send Mystery Mail"):
    def __init__(self, target_user: discord.User):
        super().__init__()
        self.target_user = target_user
        self.message_input = discord.ui.TextInput(
            label="Anonymous Message",
            style=discord.TextStyle.paragraph,
            placeholder="Type your secret compliment, confession, or joke here...",
            required=True,
            max_length=1000
        )
        self.add_item(self.message_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        message_text = self.message_input.value.strip()

        # Check DND
        is_dnd = await rget(interaction.client, f"mysterymail_dnd:{self.target_user.id}")
        if is_dnd == "1":
            return await interaction.followup.send(
                "⛔ **This member has enabled Do Not Disturb and is not accepting Mystery Mail.**",
                ephemeral=True
            )

        mail_id = str(uuid.uuid4())[:8]

        # Construct DM Embed for Recipient
        dm_embed = discord.Embed(
            title="💌 You received an anonymous message",
            description=f"{message_text}\n\n**Use the button below if you want to request the sender to reveal themselves.**",
            color=0xFF69B4
        )

        view = RevealRequestView(mail_id=mail_id)

        try:
            target_dm = await self.target_user.create_dm()
            await target_dm.send(embed=dm_embed, view=view)
        except discord.Forbidden:
            return await interaction.followup.send(
                "❌ **Unable to send DM to this user.** Their DMs may be closed or they have blocked the bot.",
                ephemeral=True
            )
        except Exception as e:
            return await interaction.followup.send(
                f"❌ **Failed to deliver Mystery Mail:** {e}",
                ephemeral=True
            )

        # Store Mail metadata
        mail_data = {
            "mail_id": mail_id,
            "sender_id": interaction.user.id,
            "target_id": self.target_user.id,
            "message": message_text,
            "revealed": False
        }
        await rset_json(interaction.client, f"mysterymail:{mail_id}", mail_data)

        # --- Audit Logging (Anti-Abuse Oversight) ---
        if interaction.guild:
            log_channel_id = await rget(interaction.client, f"mysterymail_log_channel:{interaction.guild.id}")
            if log_channel_id:
                try:
                    log_channel = interaction.guild.get_channel(int(log_channel_id))
                    if log_channel:
                        audit_embed = discord.Embed(
                            title="💌 Mystery Mail Audit Log",
                            color=0xFF69B4,
                            timestamp=datetime.now(timezone.utc)
                        )
                        audit_embed.add_field(name="Sender", value=f"{interaction.user.mention} (`{interaction.user.id}`)", inline=True)
                        audit_embed.add_field(name="Recipient", value=f"{self.target_user.mention} (`{self.target_user.id}`)", inline=True)
                        audit_embed.add_field(name="Message", value=f"```\n{message_text}\n```", inline=False)
                        audit_embed.set_footer(text="Mystery Mail Anti-Abuse System")
                        await log_channel.send(embed=audit_embed)
                except Exception as e:
                    print(f"Mystery Mail Audit Log Error: {e}")

        await interaction.followup.send(
            f"✨ **Mystery Mail delivered to {self.target_user.mention}!** Your identity remains 100% anonymous.",
            ephemeral=True
        )


class TargetSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)

    @discord.ui.select(
        cls=discord.ui.UserSelect,
        placeholder="Select the recipient for your Mystery Mail...",
        min_values=1,
        max_values=1
    )
    async def select_target(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        target = select.values[0]

        if target.bot:
            return await interaction.response.send_message(
                "❌ **You cannot send Mystery Mail to a bot.**",
                ephemeral=True
            )

        if target.id == interaction.user.id:
            return await interaction.response.send_message(
                "❌ **You cannot send Mystery Mail to yourself.**",
                ephemeral=True
            )

        # Check DND
        is_dnd = await rget(interaction.client, f"mysterymail_dnd:{target.id}")
        if is_dnd == "1":
            return await interaction.response.send_message(
                "⛔ **This member has enabled Do Not Disturb and is not accepting Mystery Mail.**",
                ephemeral=True
            )

        modal = MysteryMailModal(target_user=target)
        await interaction.response.send_modal(modal)


class RevealRequestView(discord.ui.View):
    def __init__(self, mail_id: str):
        super().__init__(timeout=None)
        self.mail_id = mail_id

    @discord.ui.button(label="Request to Reveal", style=discord.ButtonStyle.secondary, custom_id="mm_btn_request_reveal")
    async def request_reveal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        mail_data = await rget_json(interaction.client, f"mysterymail:{self.mail_id}")
        if not mail_data:
            return await interaction.followup.send("❌ This Mystery Mail record is no longer active.", ephemeral=True)

        if mail_data.get("revealed"):
            return await interaction.followup.send("✨ The sender has already revealed their identity!", ephemeral=True)

        sender_id = mail_data.get("sender_id")
        sender = interaction.client.get_user(sender_id) or await interaction.client.fetch_user(sender_id)

        if not sender:
            return await interaction.followup.send("❌ Unable to reach the sender.", ephemeral=True)

        # Send decision DM to Sender
        sender_decision_embed = discord.Embed(
            title="📩 Identity Reveal Requested!",
            description=(
                f"{interaction.user.mention} received your Mystery Mail:\n"
                f"> *\"{mail_data.get('message')}\"*\n\n"
                "**They are asking to reveal your identity. Would you like to accept?**"
            ),
            color=0xFF69B4
        )

        decision_view = SenderDecisionView(mail_id=self.mail_id, recipient_id=interaction.user.id)

        try:
            sender_dm = await sender.create_dm()
            await sender_dm.send(embed=sender_decision_embed, view=decision_view)
            await interaction.followup.send(
                "✨ **Reveal request sent to the sender!** You will be notified if they accept.",
                ephemeral=True
            )
        except Exception:
            await interaction.followup.send(
                "❌ Could not deliver reveal request to sender (DMs closed).",
                ephemeral=True
            )


class SenderDecisionView(discord.ui.View):
    def __init__(self, mail_id: str, recipient_id: int):
        super().__init__(timeout=None)
        self.mail_id = mail_id
        self.recipient_id = recipient_id

    @discord.ui.button(label="Accept & Reveal Identity", style=discord.ButtonStyle.success, custom_id="mm_btn_accept_reveal")
    async def accept_reveal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        mail_data = await rget_json(interaction.client, f"mysterymail:{self.mail_id}")
        if not mail_data:
            return await interaction.followup.send("❌ Mystery Mail record not found.", ephemeral=True)

        mail_data["revealed"] = True
        await rset_json(interaction.client, f"mysterymail:{self.mail_id}", mail_data)

        recipient = interaction.client.get_user(self.recipient_id) or await interaction.client.fetch_user(self.recipient_id)

        if recipient:
            revealed_embed = discord.Embed(
                title="💖 Sender Revealed",
                description=(
                    f"This person sent that message to you: {interaction.user.mention}\n\n"
                    f"**Original message**\n{mail_data.get('message')}"
                ),
                color=0xFF69B4
            )
            try:
                recipient_dm = await recipient.create_dm()
                await recipient_dm.send(embed=revealed_embed)
            except: pass

        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)

        await interaction.followup.send(
            f"💖 **Identity revealed!** {recipient.mention if recipient else 'The recipient'} can now see who sent the message.",
            ephemeral=True
        )

    @discord.ui.button(label="Keep Anonymous", style=discord.ButtonStyle.danger, custom_id="mm_btn_deny_reveal")
    async def deny_reveal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        recipient = interaction.client.get_user(self.recipient_id) or await interaction.client.fetch_user(self.recipient_id)

        if recipient:
            try:
                recipient_dm = await recipient.create_dm()
                await recipient_dm.send("🔒 **The sender chose to remain anonymous.**")
            except: pass

        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)

        await interaction.followup.send(
            "🔒 **You chose to stay anonymous.**",
            ephemeral=True
        )


class MysteryMailPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Send Mystery Mail", style=discord.ButtonStyle.secondary, custom_id="mm_panel_send_mail")
    async def send_mail_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = TargetSelectView()
        await interaction.response.send_message(
            "💌 Select who you want to send an anonymous Mystery Mail to:",
            view=view,
            ephemeral=True
        )

    @discord.ui.button(label="Toggle Do Not Disturb", style=discord.ButtonStyle.danger, custom_id="mm_panel_toggle_dnd")
    async def toggle_dnd_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        key = f"mysterymail_dnd:{interaction.user.id}"
        current = await rget(interaction.client, key)

        if current == "1":
            await rdelete(interaction.client, key)
            await interaction.response.send_message(
                "✅ **You have disabled Do Not Disturb for Mystery Mail.** You can now receive anonymous messages.",
                ephemeral=True
            )
        else:
            await rset(interaction.client, key, "1")
            await interaction.response.send_message(
                "⛔ **You have enabled Do Not Disturb for Mystery Mail.** You will no longer receive anonymous messages.",
                ephemeral=True
            )


class MysteryMail(commands.Cog):
    """
    Mystery Mail Anonymous Messaging System.
    Allows members to send anonymous compliments, confessions, or notes with reveal requests.
    """
    def __init__(self, bot):
        self.bot = bot
        self.bot.add_view(MysteryMailPanelView())

    @app_commands.command(name="mysterymail", description="Display the interactive Mystery Mail panel.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def mysterymail_cmd(self, interaction: discord.Interaction):
        embed = discord.Embed(
            description=(
                "*Ever wondered who's been thinking about you?*\n\n"
                "**Receive anonymous messages from other members and try to figure out who sent them. "
                "Whether it's a compliment, a confession, a joke, or just someone wanting to make you smile, "
                "every message is delivered privately by the bot.**\n\n"
                "# __How it works__\n\n"
                "♡ Receive anonymous messages in your DMs.\n"
                "♡ Decide if you want to guess who sent it.\n"
                "♡ Keep everyone guessing while staying anonymous.\n\n"
                "*Note: Staff can see your identity for moderation purposes.*\n\n"
                "━━━━━━━ ✦ ━━━━━━━"
            ),
            color=0xFF69B4
        )

        view = MysteryMailPanelView()

        if os.path.exists(HYACINE_BANNER_PATH):
            file = discord.File(HYACINE_BANNER_PATH, filename="banner.png")
            embed.set_image(url="attachment://banner.png")
            await interaction.response.send_message(embed=embed, file=file, view=view)
        else:
            embed.set_image(url=HYACINE_BANNER_CDN)
            await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="mysterymaillog", description="Set the audit log channel for Mystery Mail anti-abuse oversight.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def mysterymaillog_cmd(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await rset(interaction.client, f"mysterymail_log_channel:{interaction.guild.id}", str(channel.id))
        await interaction.response.send_message(
            f"✅ **Mystery Mail audit log channel updated to {channel.mention}.** All sent anonymous messages will be logged here for admin oversight.",
            ephemeral=True
        )

    @app_commands.command(name="mysterymaillogclear", description="Disable Mystery Mail audit logging.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def mysterymaillogclear_cmd(self, interaction: discord.Interaction):
        await rdelete(interaction.client, f"mysterymail_log_channel:{interaction.guild.id}")
        await interaction.response.send_message(
            "🗑️ **Mystery Mail audit logging disabled for this server.**",
            ephemeral=True
        )

async def setup(bot):
    if "MysteryMail" not in bot.cogs:
        await bot.add_cog(MysteryMail(bot))

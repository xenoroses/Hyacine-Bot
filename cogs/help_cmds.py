import discord
from discord.ext import commands
from discord.ui import Select, View
from typing import Union, Optional

CATEGORY_METADATA = {
    "Staff": {"icon": "✧", "name": "Stellar Decrees"},
    "Fun": {"icon": "❂", "name": "Aether Waves"},
    "Owner": {"icon": "❖", "name": "Sovereign Essence"},
    "Sticky": {"icon": "📌", "name": "Pinned Beacons"},
    "AFK": {"icon": "🌙", "name": "Dormancy Protocol"},
    "AIUtility": {"icon": "🤖", "name": "Simulated Intelligence"},
    "Impersonator": {"icon": "🎭", "name": "Identity Shift"},
    "AutoDelete": {"icon": "🧹", "name": "Auto Deletion"},
    "Help": {"icon": "❓", "name": "Assistance"},
    "Infrastructure": {"icon": "⚙️", "name": "System Foundation"},
    "Observability": {"icon": "⌬", "name": "Void Telemetry"},
    "Miscellaneous": {"icon": "✤", "name": "Echoes of Void"}
}

class HelpDropdown(Select):
    def __init__(self, cogs_dict):
        options = []
        for raw_cat_name, commands_list in cogs_dict.items():
            meta = CATEGORY_METADATA.get(raw_cat_name, {"icon": "✦", "name": raw_cat_name})
            options.append(
                discord.SelectOption(
                    label=f"{meta['icon']} {meta['name']}", 
                    description=f"{len(commands_list)} gates",
                    value=raw_cat_name
                )
            )
        super().__init__(placeholder="Select a sector to view logic gates...", options=options)
        self.cogs_dict = cogs_dict

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        selected_category = self.values[0]
        commands_list = self.cogs_dict[selected_category]
        meta = CATEGORY_METADATA.get(selected_category, {"icon": "✦", "name": selected_category})
        
        embed = discord.Embed(title=f"{meta['icon']} {meta['name']}", color=0x9B59B6)
        description = f"**Logic Gates ({len(commands_list)})**\n\n"
        for cmd in commands_list:
            doc = cmd.description or "No documentation archived."
            description += f"`/{cmd.name}`\n{doc}\n\n"
        
        embed.description = description[:4096]
        try:
            await interaction.message.edit(embed=embed)
        except:
            await interaction.followup.send(f"**{meta['name']}**\n{description[:1900]}", ephemeral=True)

class HelpCommands(commands.Cog):
    """
    Premium Help UI Overlay.
    Hardened for multi-permission environments with 'Stellar Matrix' fallback.
    """
    def __init__(self, bot):
        self.bot = bot

    async def _send_embed(self, dest: Union[discord.abc.Messageable, commands.Context], embed: discord.Embed, view: Optional[View] = None, ephemeral: bool = False, fallback_text: Optional[str] = None):
        """Standardized robust response handler for all engines."""
        send_method = dest.send if hasattr(dest, "send") else dest
        supports_ephemeral = isinstance(dest, (commands.Context, discord.Interaction)) or (hasattr(dest, "interaction") and dest.interaction)

        try:
            if supports_ephemeral:
                await send_method(embed=embed, view=view, ephemeral=ephemeral)
            else:
                await send_method(embed=embed, view=view)
        except discord.Forbidden:
            content = fallback_text or embed.description or "Action Processing..."
            header = "⌬ ⟡ **𝒮𝓎𝓈𝓉ℯ𝓂 𝒜𝓊𝒹𝒾𝓉 (𝒫𝓁𝒶𝒾𝓃-𝒯ℯ𝓍𝓉 ℳℴ𝒹ℯ)**\n"
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

    @commands.hybrid_command(name="help", description="Discover everything Hyacine can do.")
    async def help_command(self, ctx: commands.Context):
        await ctx.defer()
        cogs_dict = {}
        for cog_name, cog in self.bot.cogs.items():
            clean_name = cog_name.replace("Commands", "").replace("Engine", "").strip()
            cmds = cog.get_commands()
            if cmds: cogs_dict[clean_name] = cmds
            
        embed = discord.Embed(
            title="Commands for Hyacine",
            description="**» Help menu**\nSelect a category below to explore internal logic gates.",
            color=0x9B59B6
        )
        
        cat_str = ""
        categories = list(cogs_dict.keys())
        for i in range(0, len(categories), 2):
            pair = categories[i:i+2]
            cat_str += f"• {pair[0]:<20} "
            if len(pair) > 1: cat_str += f"• {pair[1]:<20}"
            cat_str += "\n"
            
        embed.add_field(name="**» Sectors**", value=f"```\n{cat_str}\n```", inline=False)
        embed.set_footer(text="© Hyacine Protocol | Stellar Symphony Index")
        
        view = View(timeout=120)
        view.add_item(HelpDropdown(cogs_dict))
        
        await self._send_embed(ctx, embed, view=view, fallback_text=f"ℋ𝓎𝒶𝒫𝒾𝓃ℯ ℋℯ𝓁𝓅 𝒸𝒶𝓉ℯ𝑔ℴ𝓇𝒾ℯ𝓈:\n{cat_str}")

async def setup(bot):
    for cmd_name in ['help', 'Help', 'HELP']:
        try: bot.remove_command(cmd_name)
        except: pass
    if "HelpCommands" not in bot.cogs:
        await bot.add_cog(HelpCommands(bot))

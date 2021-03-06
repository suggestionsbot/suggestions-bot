const { MessageEmbed } = require('discord.js-light');
const Command = require('../../structures/Command');
const { version, description } = require('../../../package.json');

module.exports = class InfoCommand extends Command {
  constructor(client) {
    super(client, {
      name: 'info',
      category: 'General',
      description: 'View bot information.',
      aliases: ['botinfo'],
      botPermissions: ['ADD_REACTIONS', 'EMBED_LINKS'],
      guildOnly: false,
      guarded: true
    });
  }

  async run(message, args) {

    const { colors, discord, owners, website, github, legal } = this.client.config;

    const embed = new MessageEmbed()
      .setTitle(this.client.user.username)
      .setDescription(description)
      .setColor(colors.main)
      .setThumbnail(this.client.user.avatarURL())
      .addField(owners.length <= 1 ? 'Bot Author' : 'Bot Author(s)',
        owners.map(o => `${this.client.users.forge(o.id)} \`[${o.tag}]\``).join('\n'))
      .addField('Website', `[suggestions.gg](${website})`)
      .addField('Discord', `[suggestions.gg/discord](${discord})`)
      .addField('GitHub', `[suggestions.gg/github](${github})`)
      .addField('Legal', `[Privacy Policy](${legal.privacy}) | [Terms of Service](${legal.terms})`)
      .addField('Version', version)
      .setFooter('© 2022 Anthony Collier');

    return message.channel.send(embed);
  }
};

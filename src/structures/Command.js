module.exports = class Command {
  constructor(client, {
    name = null,
    description = null,
    category = null,
    usage = null,
    enabled = true,
    guarded = false,
    guildOnly = true,
    staffOnly = false,
    adminOnly = false,
    ownerOnly = false,
    superSecretOnly = false,
    supportOnly = false,
    aliases = new Array(),
    botPermissions = new Array(),
    throttles = new Map(),
    throttling = { usages: 2, duration: 5 } || false
  }) {
    this.client = client;
    this.conf = { enabled, guarded, guildOnly, staffOnly, adminOnly, ownerOnly, superSecretOnly, supportOnly, aliases, botPermissions, throttles, throttling };
    this.help = { name, description, category, usage };
  }

  throttle(userID) {

    if (!this.conf.throttling || this.client.isOwner(userID)) return;

    let throttle = this.conf.throttles.get(userID);
    if (!throttle) {
      throttle = {
        start: Date.now(),
        usages: 0,
        timeout: this.client.wait(this.conf.throttling.duration * 1000).then(() => {
          this.conf.throttles.delete(userID);
        })
      };
      this.conf.throttles.set(userID, throttle);
    }
    return throttle;
  }
};

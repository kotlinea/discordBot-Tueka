"""Shared authenticated poll operations and privacy-safe result/export projection."""
import csv
import io
import json
from .models import Actor, PollError, disclose, permissions


class PollService:
    def __init__(self, repository):
        self.repository = repository

    def permissions(self, actor):
        settings = self.repository.settings.get_module(actor.guild_id, 'advanced_polls')['settings']
        return permissions(actor,settings)

    def require(self, actor, permission):
        if actor.bot or permission not in self.permissions(actor):
            raise PollError('forbidden')

    def read(self, actor, poll_id, *, management=False):
        return self.repository.read(actor,poll_id,management=management)

    def vote(self, actor, poll_id, choices, message_id):
        poll = self.repository.vote(actor.guild_id, poll_id, actor.user_id, choices, roles=actor.roles,
                                    bot=actor.bot, message_id=message_id)
        return disclose(poll)

    def create(self, actor, channel, config, request_key, **timing):
        self.require(actor, 'manage')
        return self.repository.create(actor.guild_id, channel, actor.user_id, config, request_key, principal=actor, **timing)

    def edit(self, actor, poll, config, revision, **timing):
        self.require(actor, 'manage')
        return self.repository.edit(actor.guild_id, poll, actor.user_id, config, revision, principal=actor, **timing)

    def transition(self, actor, poll, action, revision, **timing):
        self.require(actor, 'manage')
        return self.repository.transition(actor.guild_id, poll, actor.user_id, action, revision, principal=actor, **timing)

    def export(self, actor, poll, format):
        result = self.read(actor, poll, management=True)
        if format == 'json':
            return json.dumps(result, ensure_ascii=False, indent=2).encode('utf-8')
        if format != 'csv':
            raise PollError('invalid')
        output = io.StringIO(newline='')
        writer = csv.writer(output)
        def safe(value):
            value = str(value)
            return "'"+value if value.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')) else value
        writer.writerow(['question', safe(result['config']['question'])])
        writer.writerow(['option', 'count', 'weighted_count'])
        for index, option in enumerate(result['config']['options']):
            writer.writerow([safe(option), result.get('counts', ['']*len(result['config']['options']))[index], result.get('weighted_counts', ['']*len(result['config']['options']))[index]])
        if 'ballots' in result:
            writer.writerow(['user_id', 'choices', 'weight'])
            for ballot in result['ballots']:
                writer.writerow([ballot['user_id'], '|'.join(str(index+1) for index in ballot['choices']), ballot['weight']])
        elif 'participants' in result:
            writer.writerow(['participant'])
            writer.writerows([[user] for user in result['participants']])
        return ('\ufeff'+output.getvalue()).encode('utf-8')

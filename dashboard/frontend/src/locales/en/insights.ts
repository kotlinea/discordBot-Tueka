export default {insights:{
  'title':'Server Insights','home':'Activity report','settings':'Collection settings','refresh':'Refresh settings',
  'help':'Review observed messages, membership changes, and voice connection time by UTC day. Unobserved days differ from zero.',
  'utc':'Dates use UTC. Select up to 90 days inside the retention window.','start':'Start date (UTC)','end':'End date (UTC)','apply':'Show period',
  'metric':'Chart metric','messages':'Messages','joins':'Joins','leaves':'Leaves','voice_seconds':'Voice connection time (seconds)','observed_seconds':'Observed time (seconds)',
  'day':'UTC date','unknown':'Not observed','chart':'Daily activity chart','table':'Daily aggregates',
  'collecting':'Observation confirmed within the last 90 seconds.','lastObserved':'Last observation confirmation','waiting':'Current observation is unconfirmed. Check the Bot connection and collection settings.','off':'Collection is OFF. Retained reports remain available.',
  'coverage':'Observation gaps are not filled in. Partial observation does not represent a complete day of server activity. Voice measures connection duration rather than speech.',
  'noData':'No observations in this period. Collection starts with new events after it is enabled.',
  'enabled':'Enable collection','channels':'Channels to observe','members':'Count joins and leaves','retention':'Retention days',
  'settingsHelp':'Message bodies, attachments, display names, and audio content are not stored. Bots/webhooks, NSFW, private threads, and AFK are excluded.',
  'channelHelp':'Up to 25 channels. An empty selection records no messages or voice time. Public threads follow the selected parent.',
  'retentionHelp':'1–365 days. Shortening retention deletes old aggregates, including while collection is OFF. Deleted reports cannot be restored by increasing retention.',
}}

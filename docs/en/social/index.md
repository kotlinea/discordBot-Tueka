# Social notifications

Server managers select a provider, account ID/handle and notification channel. Select mention roles in the dedicated field rather than inserting mentions into message text.

Save, then wait for pending to become active. Initial past posts are not announced. Use Preview for event templates. The default limit is ten accounts per provider/server; availability and limits are controlled by the operator.

Supported variables: `{account}`, `{handle}`, `{title}`, `{text}`, `{url}`, `{platform}`, `{event}`, `{published_at}`, `{thumbnail}`, `{avatar}`, `{viewer_count}`.

Repair missing channels or Bot permissions. For persistent failures, give the operator the provider, target, time and displayed state.

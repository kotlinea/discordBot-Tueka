# Create and reuse moderation rules

Open AutoMod, Anti-Spam or Anti-Raid under Moderation. You can create multiple rules with the same detection method and give each rule different channels, thresholds and actions.

## Create or duplicate

1. Open **Create rule**. Select a detection method under **Start from defaults**, then choose **Load defaults**.
2. Enter a name, detection settings, scope, exemptions and actions. Review and save. New rules are disabled.
3. To reuse a rule, choose **Duplicate draft** in the list, change its name or scope, and save. Opening a draft neither creates a rule nor changes the source.

Loading defaults asks before replacing an unsaved draft. Failed reads and saves preserve your input. If a selected channel or role becomes unavailable, use the displayed ID to identify it and select an available resource.

## Switch saved rules together

1. Select rules in the list. **Select visible rules** selects the current search results.
2. Choose **Enable selected** or **Disable selected**.
3. Review the count, monitor/enforce modes, required permissions and execution conditions, then choose **Confirm state change**.

Rules keep their contents, order and history when stopped and enabled again. You do not need to recreate them. This changes saved states; it does not immediately run actions such as bans. If the parent Moderation setting or the family is disabled, enabling rules does not start protection. Bot permissions, available resources and role hierarchy must also permit execution.

Save or discard pending order and deletion edits before selecting rules. Duplicate submissions and navigation are blocked while the state change is pending.

If another manager has changed a selected rule, the entire request leaves the rules unchanged. Choose **Reload and review selection**, review the latest values and confirm again. Deleted rules are removed from the selection on reload. Permission and validation errors also preserve the selection.

Related: [AutoMod](../features/automod.md), [Anti-Spam](../features/anti-spam.md), [Anti-Raid](../features/anti-raid.md), [Saving and conflicts](saving.md)

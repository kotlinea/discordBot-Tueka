# Saving and conflicts

Settings show an unsaved notice and Save/Discard controls. Use the footer in a dialog or the save bar on a settings page. Inputs and repeated submissions are disabled while saving. A successful save refreshes the server values.

Your input stays in place when settings change on the server. Discard restores the latest loaded values. Links, search navigation and the browser Back button ask before leaving an edited page. Use Try again after a read failure.

Rule deletion marks and ordering changes are applied when saved. If deletion fails partway through, the page shows the number already deleted and retains the remaining changes. Retry processes only the remainder. Discard cannot undo successful deletions. Operations such as subscription deletion are sent after their confirmation.

## Configuration and execution conditions

Configured ON is a saved setting. Check parent features, required permissions and settings, missing channels or roles, and whether any rules are enabled. Unavailable selections retain their IDs so you can choose a valid replacement. A failed or unknown read does not mean disabled or healthy.

Social's Account verified and Reaction Roles' Published messages describe their respective states. Also check destinations, feature settings and provider availability. When an operation reports Request accepted, check its processing result in the list.

## Conflict (409)

Another manager saved a newer revision. Preserve your intended edits and fetch the latest settings. Your draft is retained until you explicitly discard it or reload the page. Compare and reapply your changes to the latest values. There is no force-overwrite operation.

For 403, check your access and permissions. Failed saves with 403, 409 or 422 preserve the current screen's input. A 401 requires signing in again. Drafts are not stored persistently on your device; copy any changes you need before signing in again or reloading.

## Validation (422)

Correct the highlighted field: invalid values, conflicting actions, wrong-server resources or role hierarchy. Resources from another server cannot be saved.

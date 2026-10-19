# All Discord commands

Find each command’s purpose, arguments, permissions and response visibility. Replace example IDs and targets with your server resources. Try sanction/deletion examples only in a test server.

## /apply

- **Purpose**: Choose an accepting application form and answer in a private modal.
- **Arguments (* required)**: form*:string
- **Permissions**: Server member meeting the form's role and age requirements at submission time.
- **Response**: Privately displays the submission number.
- **When disabled**: Refuses submissions while intake or the form is disabled.
- **Example**: `/apply form:1`

## /application-status

- **Purpose**: Check your latest ten applications within retention, or withdraw an open application using withdraw_id.
- **Arguments (* required)**: withdraw_id:integer
- **Permissions**: The applicant, within the server.
- **Response**: Privately displays status or the withdrawal result.
- **When disabled**: Status remains readable. Withdrawals pause while intake is disabled.
- **Example**: `/application-status`

## /ban

- **Purpose**: Ban a member.
- **Arguments (* required)**: member*:user, reason:string
- **Permissions**: ban_members; Bot permissions and role hierarchy also apply.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/ban member:@TestMember`

## /calculate

- **Purpose**: Evaluate arithmetic and exponentiation.
- **Arguments (* required)**: expression*:string
- **Permissions**: Members with access to the server/channel.
- **Response**: Public response; errors are private.
- **When disabled**: Core command; access and execution-context restrictions still apply.
- **Example**: `/calculate expression:2+3*4`

## /clear

- **Purpose**: Delete messages in this channel after confirmation.
- **Arguments (* required)**: confirm:string
- **Permissions**: manage_messages; Bot permissions and role hierarchy also apply.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/clear confirm:confirm`

## /clear_trust_score

- **Purpose**: Clear trust events while retaining sanction history.
- **Arguments (* required)**: member*:user
- **Permissions**: manage_guild; Bot permissions and role hierarchy also apply.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/clear_trust_score member:@TestMember`

## /echo

- **Purpose**: Build and send an embed with the supplied fields.
- **Arguments (* required)**: title:string, description:string, color:string, url:string, author_name:string, author_url:string, author_icon_url:string, footer_text:string, footer_icon_url:string, thumbnail_url:string, image_url:string, fields_json:string, timestamp:boolean = false, ephemeral:boolean = false
- **Permissions**: Members with access to the server/channel.
- **Response**: The ephemeral argument selects private or public response.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/echo`

## /gemini

- **Purpose**: Ask Gemini a question.
- **Arguments (* required)**: message*:string
- **Permissions**: Members with access to the server/channel.
- **Response**: Responses and generation errors are public. Replies over 2000 characters are sent as a text file, with mentions disabled. The unconfigured notice is private.
- **When disabled**: Unavailable unless enabled/configured by the system operator.
- **Example**: `/gemini message:Hello`

## /help

- **Purpose**: List available commands; all:true includes disabled features.
- **Arguments (* required)**: all:boolean = false
- **Permissions**: Members with access to the server/channel.
- **Response**: Private when all:false; public when all:true.
- **When disabled**: Core command; access and execution-context restrictions still apply.
- **Example**: `/help`

## /kick

- **Purpose**: Kick a member.
- **Arguments (* required)**: member*:user, reason:string
- **Permissions**: kick_members; Bot permissions and role hierarchy also apply.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/kick member:@TestMember`

## /leaderboard

- **Purpose**: Show text XP rankings.
- **Arguments (* required)**: —
- **Permissions**: Members with access to the server/channel.
- **Response**: Public response; errors are private.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/leaderboard`

## /mod ban

- **Purpose**: Ban a member.
- **Arguments (* required)**: member*:user, reason:string
- **Permissions**: ban_members; Bot permissions and role hierarchy also apply.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/mod ban member:@TestMember`

## /mod kick

- **Purpose**: Kick a member.
- **Arguments (* required)**: member*:user, reason:string
- **Permissions**: kick_members; Bot permissions and role hierarchy also apply.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/mod kick member:@TestMember`

## /mod lock

- **Purpose**: Lock role changes or a channel.
- **Arguments (* required)**: channel:channel, reason:string
- **Permissions**: manage_channels; Bot permissions and role hierarchy also apply.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/mod lock`

## /mod lockdown

- **Purpose**: Lock down the server temporarily.
- **Arguments (* required)**: minutes:integer [1..1440] = 30, reason:string
- **Permissions**: administrator; Bot permissions and role hierarchy also apply.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/mod lockdown`

## /mod purge

- **Purpose**: Delete recent messages.
- **Arguments (* required)**: count*:integer [1..100], reason:string
- **Permissions**: manage_messages; Bot permissions and role hierarchy also apply.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/mod purge count:1`

## /mod softban

- **Purpose**: Ban then unban a member.
- **Arguments (* required)**: member*:user, reason:string
- **Permissions**: ban_members; Bot permissions and role hierarchy also apply.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/mod softban member:@TestMember`

## /mod timeout

- **Purpose**: Set a timeout.
- **Arguments (* required)**: member*:user, minutes*:integer [1..40320], reason:string
- **Permissions**: moderate_members; Bot permissions and role hierarchy also apply.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/mod timeout member:@TestMember minutes:5`

## /mod unban

- **Purpose**: Unban a user ID.
- **Arguments (* required)**: user_id*:string, reason:string
- **Permissions**: ban_members; Bot permissions and role hierarchy also apply.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/mod unban user_id:123456789012345678`

## /mod unlock

- **Purpose**: Unlock role changes or a channel.
- **Arguments (* required)**: channel:channel, reason:string
- **Permissions**: manage_channels; Bot permissions and role hierarchy also apply.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/mod unlock`

## /mod unlockdown

- **Purpose**: Release the active lockdown.
- **Arguments (* required)**: reason:string
- **Permissions**: administrator; Bot permissions and role hierarchy also apply.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/mod unlockdown`

## /mod untimeout

- **Purpose**: Remove a timeout.
- **Arguments (* required)**: member*:user, reason:string
- **Permissions**: moderate_members; Bot permissions and role hierarchy also apply.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/mod untimeout member:@TestMember`

## /mod warn

- **Purpose**: Add a warning.
- **Arguments (* required)**: member*:user, reason:string
- **Permissions**: moderate_members; Bot permissions and role hierarchy also apply.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/mod warn member:@TestMember`

## /ping

- **Purpose**: Measure Bot latency.
- **Arguments (* required)**: —
- **Permissions**: Members with access to the server/channel.
- **Response**: Public response; errors are private.
- **When disabled**: Core command; access and execution-context restrictions still apply.
- **Example**: `/ping`

## /poll

- **Purpose**: Create a poll; separate up to ten choices with |.
- **Arguments (* required)**: question*:string, options*:string, duration_minutes:integer [1..10080], image_url:string
- **Permissions**: manage_guild; Bot permissions and role hierarchy also apply.
- **Response**: Public response; errors are private.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/poll question:Lunch? options:A|B`

## /r add

- **Purpose**: Add the selected member or mapping.
- **Arguments (* required)**: config_id*:integer, emoji*:string, role*:role
- **Permissions**: Manage Server; Bot Manage Roles and role hierarchy are also required.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/r add config_id:1 emoji:✅ role:@TestRole`

## /r addmany

- **Purpose**: Open a form to add multiple emoji/role mappings.
- **Arguments (* required)**: config_id*:integer
- **Permissions**: Manage Server; Bot Manage Roles and role hierarchy are also required.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/r addmany config_id:1`

## /r aio

- **Purpose**: Create a message and mappings together.
- **Arguments (* required)**: channel*:channel, emoji*:string, role*:role
- **Permissions**: Manage Server; Bot Manage Roles and role hierarchy are also required.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/r aio channel:#test emoji:✅ role:@TestRole`

## /r aioi

- **Purpose**: Create an AIO message with binding behavior.
- **Arguments (* required)**: channel*:channel, emoji*:string, role*:role
- **Permissions**: Manage Server; Bot Manage Roles and role hierarchy are also required.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/r aioi channel:#test emoji:✅ role:@TestRole`

## /r aiou

- **Purpose**: Create an AIO message with unique behavior.
- **Arguments (* required)**: channel*:channel, emoji*:string, role*:role
- **Permissions**: Manage Server; Bot Manage Roles and role hierarchy are also required.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/r aiou channel:#test emoji:✅ role:@TestRole`

## /r aiov

- **Purpose**: Create an AIO message with verify behavior.
- **Arguments (* required)**: channel*:channel, emoji*:string, role*:role
- **Permissions**: Manage Server; Bot Manage Roles and role hierarchy are also required.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/r aiov channel:#test emoji:✅ role:@TestRole`

## /r binding

- **Purpose**: Use binding behavior.
- **Arguments (* required)**: config_id*:integer
- **Permissions**: Manage Server; Bot Manage Roles and role hierarchy are also required.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/r binding config_id:1`

## /r drop

- **Purpose**: Use drop behavior.
- **Arguments (* required)**: config_id*:integer
- **Permissions**: Manage Server; Bot Manage Roles and role hierarchy are also required.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/r drop config_id:1`

## /r fix

- **Purpose**: Repair the configured message.
- **Arguments (* required)**: config_id*:integer
- **Permissions**: Manage Server; Bot Manage Roles and role hierarchy are also required.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/r fix config_id:1`

## /r lock

- **Purpose**: Lock role changes or a channel.
- **Arguments (* required)**: config_id*:integer
- **Permissions**: Manage Server; Bot Manage Roles and role hierarchy are also required.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/r lock config_id:1`

## /r normal

- **Purpose**: Use normal behavior.
- **Arguments (* required)**: config_id*:integer
- **Permissions**: Manage Server; Bot Manage Roles and role hierarchy are also required.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/r normal config_id:1`

## /r remove

- **Purpose**: Remove the selected member or mapping.
- **Arguments (* required)**: config_id*:integer, role*:role
- **Permissions**: Manage Server; Bot Manage Roles and role hierarchy are also required.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/r remove config_id:1 role:@TestRole`

## /r reversed

- **Purpose**: Use reversed behavior.
- **Arguments (* required)**: config_id*:integer
- **Permissions**: Manage Server; Bot Manage Roles and role hierarchy are also required.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/r reversed config_id:1`

## /r show

- **Purpose**: Show configuration.
- **Arguments (* required)**: config_id*:integer
- **Permissions**: Manage Server; Bot Manage Roles and role hierarchy are also required.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/r show config_id:1`

## /r temp

- **Purpose**: Set a temporary role duration.
- **Arguments (* required)**: config_id*:integer, minutes*:integer
- **Permissions**: Manage Server; Bot Manage Roles and role hierarchy are also required.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/r temp config_id:1 minutes:5`

## /r unique

- **Purpose**: Use unique behavior.
- **Arguments (* required)**: config_id*:integer
- **Permissions**: Manage Server; Bot Manage Roles and role hierarchy are also required.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/r unique config_id:1`

## /r unlock

- **Purpose**: Unlock role changes or a channel.
- **Arguments (* required)**: config_id*:integer
- **Permissions**: Manage Server; Bot Manage Roles and role hierarchy are also required.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/r unlock config_id:1`

## /r verify

- **Purpose**: Use verify behavior.
- **Arguments (* required)**: config_id*:integer
- **Permissions**: Manage Server; Bot Manage Roles and role hierarchy are also required.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/r verify config_id:1`

## /rank

- **Purpose**: Show your text XP rank.
- **Arguments (* required)**: —
- **Permissions**: Members with access to the server/channel.
- **Response**: Public response; errors are private.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/rank`

## /reactionrole add

- **Purpose**: Add the selected member or mapping.
- **Arguments (* required)**: config_id*:integer, emoji*:string, role*:role
- **Permissions**: Manage Server; Bot Manage Roles and role hierarchy are also required.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/reactionrole add config_id:1 emoji:✅ role:@TestRole`

## /reactionrole addmany

- **Purpose**: Open a form to add multiple emoji/role mappings.
- **Arguments (* required)**: config_id*:integer
- **Permissions**: Manage Server; Bot Manage Roles and role hierarchy are also required.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/reactionrole addmany config_id:1`

## /reactionrole aio

- **Purpose**: Create a message and mappings together.
- **Arguments (* required)**: channel*:channel, emoji*:string, role*:role, behavior:string = "normal", title:string = "ロールを選択"
- **Permissions**: Manage Server; Bot Manage Roles and role hierarchy are also required.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/reactionrole aio channel:#test emoji:✅ role:@TestRole`

## /reactionrole blacklist add

- **Purpose**: Add the selected member or mapping. Target: denied roles.
- **Arguments (* required)**: config_id*:integer, role*:role
- **Permissions**: Manage Server; Bot Manage Roles and role hierarchy are also required.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/reactionrole blacklist add config_id:1 role:@TestRole`

## /reactionrole blacklist clear

- **Purpose**: Clear the access list. Target: denied roles.
- **Arguments (* required)**: config_id*:integer
- **Permissions**: Manage Server; Bot Manage Roles and role hierarchy are also required.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/reactionrole blacklist clear config_id:1`

## /reactionrole blacklist remove

- **Purpose**: Remove the selected member or mapping. Target: denied roles.
- **Arguments (* required)**: config_id*:integer, role*:role
- **Permissions**: Manage Server; Bot Manage Roles and role hierarchy are also required.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/reactionrole blacklist remove config_id:1 role:@TestRole`

## /reactionrole channel

- **Purpose**: Create a reaction-role channel.
- **Arguments (* required)**: name:string = "roles"
- **Permissions**: Manage Server; Bot Manage Roles and role hierarchy are also required.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/reactionrole channel`

## /reactionrole create

- **Purpose**: Create a reaction-role message.
- **Arguments (* required)**: channel*:channel, emoji*:string, role*:role, title:string = "ロールを選択", message_id:string
- **Permissions**: Manage Server; Bot Manage Roles and role hierarchy are also required.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/reactionrole create channel:#test emoji:✅ role:@TestRole`

## /reactionrole link create

- **Purpose**: Create a linked message group.
- **Arguments (* required)**: name*:string, message_ids*:string
- **Permissions**: Manage Server; Bot Manage Roles and role hierarchy are also required.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/reactionrole link create name:test message_ids:123456789012345678`

## /reactionrole link list

- **Purpose**: List linked groups.
- **Arguments (* required)**: —
- **Permissions**: Manage Server; Bot Manage Roles and role hierarchy are also required.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/reactionrole link list`

## /reactionrole link unlink

- **Purpose**: Remove the link group.
- **Arguments (* required)**: group_id*:integer
- **Permissions**: Manage Server; Bot Manage Roles and role hierarchy are also required.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/reactionrole link unlink group_id:1`

## /reactionrole manage color

- **Purpose**: Change embed color.
- **Arguments (* required)**: config_id*:integer, color*:string
- **Permissions**: Manage Server; Bot Manage Roles and role hierarchy are also required.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/reactionrole manage color config_id:1 color:#336699`

## /reactionrole manage edit

- **Purpose**: Edit the message embed.
- **Arguments (* required)**: config_id*:integer, title*:string, description:string = ""
- **Permissions**: Manage Server; Bot Manage Roles and role hierarchy are also required.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/reactionrole manage edit config_id:1 title:Test`

## /reactionrole manage fix

- **Purpose**: Repair the configured message.
- **Arguments (* required)**: config_id*:integer
- **Permissions**: Manage Server; Bot Manage Roles and role hierarchy are also required.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/reactionrole manage fix config_id:1`

## /reactionrole manage fixforeign

- **Purpose**: Repair reaction-role bindings for external emoji.
- **Arguments (* required)**: config_id*:integer
- **Permissions**: Manage Server; Bot Manage Roles and role hierarchy are also required.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/reactionrole manage fixforeign config_id:1`

## /reactionrole manage move

- **Purpose**: Move the configuration to another message.
- **Arguments (* required)**: config_id*:integer, channel*:channel, message_id*:string
- **Permissions**: Manage Server; Bot Manage Roles and role hierarchy are also required.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/reactionrole manage move config_id:1 channel:#test message_id:123456789012345678`

## /reactionrole manage reset-binding

- **Purpose**: Clear a member’s binding.
- **Arguments (* required)**: config_id*:integer, user*:user
- **Permissions**: Manage Server; Bot Manage Roles and role hierarchy are also required.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/reactionrole manage reset-binding config_id:1 user:@TestMember`

## /reactionrole manage selfdestruct

- **Purpose**: Schedule configuration removal.
- **Arguments (* required)**: config_id*:integer, minutes*:integer
- **Permissions**: Manage Server; Bot Manage Roles and role hierarchy are also required.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/reactionrole manage selfdestruct config_id:1 minutes:5`

## /reactionrole manage show

- **Purpose**: Show configuration.
- **Arguments (* required)**: config_id*:integer
- **Permissions**: Manage Server; Bot Manage Roles and role hierarchy are also required.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/reactionrole manage show config_id:1`

## /reactionrole modify limit

- **Purpose**: Set the per-member selection limit.
- **Arguments (* required)**: config_id*:integer, limit*:integer
- **Permissions**: Manage Server; Bot Manage Roles and role hierarchy are also required.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/reactionrole modify limit config_id:1 limit:1`

## /reactionrole modify lock

- **Purpose**: Lock role changes or a channel.
- **Arguments (* required)**: config_id*:integer
- **Permissions**: Manage Server; Bot Manage Roles and role hierarchy are also required.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/reactionrole modify lock config_id:1`

## /reactionrole modify maxroles

- **Purpose**: Set a role membership capacity.
- **Arguments (* required)**: config_id*:integer, role*:role, maximum*:integer
- **Permissions**: Manage Server; Bot Manage Roles and role hierarchy are also required.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/reactionrole modify maxroles config_id:1 role:@TestRole maximum:10`

## /reactionrole modify type

- **Purpose**: Change the behavior type.
- **Arguments (* required)**: config_id*:integer, behavior*:string (binding, drop, normal, reversed, temp, unique, verify), duration_minutes:integer
- **Permissions**: Manage Server; Bot Manage Roles and role hierarchy are also required.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/reactionrole modify type config_id:1 behavior:normal`

## /reactionrole modify unlock

- **Purpose**: Unlock role changes or a channel.
- **Arguments (* required)**: config_id*:integer
- **Permissions**: Manage Server; Bot Manage Roles and role hierarchy are also required.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/reactionrole modify unlock config_id:1`

## /reactionrole purge

- **Purpose**: Delete recent messages.
- **Arguments (* required)**: config_id:integer
- **Permissions**: Manage Server; Bot Manage Roles and role hierarchy are also required.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/reactionrole purge`

## /reactionrole remove

- **Purpose**: Remove the selected member or mapping.
- **Arguments (* required)**: config_id*:integer, role*:role
- **Permissions**: Manage Server; Bot Manage Roles and role hierarchy are also required.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/reactionrole remove config_id:1 role:@TestRole`

## /reactionrole whitelist add

- **Purpose**: Add the selected member or mapping. Target: allowed roles.
- **Arguments (* required)**: config_id*:integer, role*:role
- **Permissions**: Manage Server; Bot Manage Roles and role hierarchy are also required.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/reactionrole whitelist add config_id:1 role:@TestRole`

## /reactionrole whitelist clear

- **Purpose**: Clear the access list. Target: allowed roles.
- **Arguments (* required)**: config_id*:integer
- **Permissions**: Manage Server; Bot Manage Roles and role hierarchy are also required.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/reactionrole whitelist clear config_id:1`

## /reactionrole whitelist remove

- **Purpose**: Remove the selected member or mapping. Target: allowed roles.
- **Arguments (* required)**: config_id*:integer, role*:role
- **Permissions**: Manage Server; Bot Manage Roles and role hierarchy are also required.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/reactionrole whitelist remove config_id:1 role:@TestRole`

## /roll

- **Purpose**: Roll a die with the specified number of sides.
- **Arguments (* required)**: sides:number = 6.0
- **Permissions**: Members with access to the server/channel.
- **Response**: Public response; errors are private.
- **When disabled**: Core command; access and execution-context restrictions still apply.
- **Example**: `/roll`

## /rps

- **Purpose**: Play rock, paper, scissors against the Bot.
- **Arguments (* required)**: hand*:string (rock, paper, scissors)
- **Permissions**: Members with access to the server/channel.
- **Response**: Public response; errors are private.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/rps hand:rock`

## /serverinfo

- **Purpose**: Show server information.
- **Arguments (* required)**: —
- **Permissions**: Members with access to the server/channel.
- **Response**: Public response; errors are private.
- **When disabled**: Core command; access and execution-context restrictions still apply.
- **Example**: `/serverinfo`

## /set_management

- **Purpose**: Select the server log channel.
- **Arguments (* required)**: channel*:channel
- **Permissions**: manage_guild; Bot permissions and role hierarchy also apply.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/set_management channel:#test`

## /suggest

- **Purpose**: Open the server suggestion form.
- **Arguments (* required)**: —
- **Permissions**: Members with access to the server/channel.
- **Response**: Private form and acknowledgement; the submitted suggestion is posted to the configured channel.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/suggest`

## /t close

- **Purpose**: Close the ticket and retain its transcript.
- **Arguments (* required)**: reason:string = "解決済み"
- **Permissions**: Opening requires panel intake/access; closing requires opener or staff access according to panel policy.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabling intake stops new tickets; existing-ticket actions follow their own access and state conditions.
- **Example**: `/t close`

## /t open

- **Purpose**: Open a ticket.
- **Arguments (* required)**: panel_id*:integer
- **Permissions**: Opening requires panel intake/access; closing requires opener or staff access according to panel policy.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/t open panel_id:1`

## /ticket add

- **Purpose**: Add the selected member or mapping.
- **Arguments (* required)**: member*:user
- **Permissions**: Authorized ticket staff/settings access; panel, team and ticket access are checked.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabling intake stops new tickets; existing-ticket actions follow their own access and state conditions.
- **Example**: `/ticket add member:@TestMember`

## /ticket blacklist

- **Purpose**: Change a member’s ticket intake restriction. Target: denied roles.
- **Arguments (* required)**: member*:user, enabled*:boolean, reason:string = "管理者による制限"
- **Permissions**: Manage Server.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabling intake stops new tickets; existing-ticket actions follow their own access and state conditions.
- **Example**: `/ticket blacklist member:@TestMember enabled:true`

## /ticket claim

- **Purpose**: Claim this ticket.
- **Arguments (* required)**: —
- **Permissions**: Authorized ticket staff/settings access; panel, team and ticket access are checked.
- **Response**: Public response in the ticket/current channel; failures are private.
- **When disabled**: Disabling intake stops new tickets; existing-ticket actions follow their own access and state conditions.
- **Example**: `/ticket claim`

## /ticket close

- **Purpose**: Close the ticket and retain its transcript.
- **Arguments (* required)**: reason:string = "解決済み"
- **Permissions**: Opening requires panel intake/access; closing requires opener or staff access according to panel policy.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabling intake stops new tickets; existing-ticket actions follow their own access and state conditions.
- **Example**: `/ticket close`

## /ticket close-request

- **Purpose**: Ask staff to approve closing.
- **Arguments (* required)**: reason:string = "解決済み"
- **Permissions**: Run inside the current ticket; approval/rejection requires staff.
- **Response**: Public response inside the ticket; failures are private.
- **When disabled**: Disabling intake stops new tickets; existing-ticket actions follow their own access and state conditions.
- **Example**: `/ticket close-request`

## /ticket join

- **Purpose**: Join a thread ticket as staff.
- **Arguments (* required)**: ticket_id*:integer
- **Permissions**: Authorized ticket staff/settings access; panel, team and ticket access are checked.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabling intake stops new tickets; existing-ticket actions follow their own access and state conditions.
- **Example**: `/ticket join ticket_id:1`

## /ticket notes

- **Purpose**: Add a staff-only note.
- **Arguments (* required)**: content*:string
- **Permissions**: Authorized ticket staff/settings access; panel, team and ticket access are checked.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabling intake stops new tickets; existing-ticket actions follow their own access and state conditions.
- **Example**: `/ticket notes content:Test note`

## /ticket on-call

- **Purpose**: Toggle automatic participation in thread tickets.
- **Arguments (* required)**: team_id*:integer, enabled*:boolean
- **Permissions**: Authorized ticket staff/settings access; panel, team and ticket access are checked.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabling intake stops new tickets; existing-ticket actions follow their own access and state conditions.
- **Example**: `/ticket on-call team_id:1 enabled:true`

## /ticket open

- **Purpose**: Open a ticket.
- **Arguments (* required)**: panel_id*:integer
- **Permissions**: Opening requires panel intake/access; closing requires opener or staff access according to panel policy.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/ticket open panel_id:1`

## /ticket remove

- **Purpose**: Remove the selected member or mapping.
- **Arguments (* required)**: member*:user
- **Permissions**: Authorized ticket staff/settings access; panel, team and ticket access are checked.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabling intake stops new tickets; existing-ticket actions follow their own access and state conditions.
- **Example**: `/ticket remove member:@TestMember`

## /ticket rename

- **Purpose**: Rename the ticket.
- **Arguments (* required)**: name*:string
- **Permissions**: A user with access to the current ticket channel/thread.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabling intake stops new tickets; existing-ticket actions follow their own access and state conditions.
- **Example**: `/ticket rename name:test`

## /ticket reopen

- **Purpose**: Reopen a closed private-thread ticket.
- **Arguments (* required)**: ticket_id*:integer
- **Permissions**: Manage Threads; a closed private-thread ticket in this server.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/ticket reopen ticket_id:1`

## /ticket setup

- **Purpose**: Open ticket settings.
- **Arguments (* required)**: —
- **Permissions**: Manage Server.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabling intake stops new tickets; existing-ticket actions follow their own access and state conditions.
- **Example**: `/ticket setup`

## /ticket stats

- **Purpose**: Show ticket statistics.
- **Arguments (* required)**: —
- **Permissions**: Manage Server.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabling intake stops new tickets; existing-ticket actions follow their own access and state conditions.
- **Example**: `/ticket stats`

## /ticket switch-panel

- **Purpose**: Switch to a panel using the same mode.
- **Arguments (* required)**: panel_id*:integer
- **Permissions**: Authorized ticket staff/settings access; panel, team and ticket access are checked.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabling intake stops new tickets; existing-ticket actions follow their own access and state conditions.
- **Example**: `/ticket switch-panel panel_id:1`

## /ticket tag

- **Purpose**: Send a configured canned response.
- **Arguments (* required)**: name*:string
- **Permissions**: A user in the server with an existing canned-response tag.
- **Response**: Public response in the ticket/current channel; failures are private.
- **When disabled**: Disabling intake stops new tickets; existing-ticket actions follow their own access and state conditions.
- **Example**: `/ticket tag name:test`

## /ticket transfer

- **Purpose**: Transfer the ticket claim.
- **Arguments (* required)**: member*:user
- **Permissions**: Authorized ticket staff/settings access; panel, team and ticket access are checked.
- **Response**: Public response inside the ticket; failures are private.
- **When disabled**: Disabling intake stops new tickets; existing-ticket actions follow their own access and state conditions.
- **Example**: `/ticket transfer member:@TestMember`

## /ticket unclaim

- **Purpose**: Release the ticket claim.
- **Arguments (* required)**: —
- **Permissions**: Inside a ticket claimed by you.
- **Response**: Public response in the ticket/current channel; failures are private.
- **When disabled**: Disabling intake stops new tickets; existing-ticket actions follow their own access and state conditions.
- **Example**: `/ticket unclaim`

## /timeout

- **Purpose**: Temporarily time out a member.
- **Arguments (* required)**: member*:user, minutes*:integer, reason:string
- **Permissions**: moderate_members; Bot permissions and role hierarchy also apply.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/timeout member:@TestMember minutes:5`

## /trust_score

- **Purpose**: Show the trust score and its reasons.
- **Arguments (* required)**: member*:user
- **Permissions**: manage_guild; Bot permissions and role hierarchy also apply.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/trust_score member:@TestMember`

## /userinfo

- **Purpose**: Show member information.
- **Arguments (* required)**: member:user
- **Permissions**: Members with access to the server/channel.
- **Response**: Public response; errors are private.
- **When disabled**: Core command; access and execution-context restrictions still apply.
- **Example**: `/userinfo`

## /vcleaderboard

- **Purpose**: Show voice XP rankings.
- **Arguments (* required)**: —
- **Permissions**: Members with access to the server/channel.
- **Response**: Public response; errors are private.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/vcleaderboard`

## /vcrank

- **Purpose**: Show your voice XP rank.
- **Arguments (* required)**: —
- **Permissions**: Members with access to the server/channel.
- **Response**: Public response; errors are private.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/vcrank`

## /warn

- **Purpose**: Warn a member.
- **Arguments (* required)**: member*:user, reason:string
- **Permissions**: moderate_members; Bot permissions and role hierarchy also apply.
- **Response**: Private confirmation; actions, posts and logs remain visible to users with access.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/warn member:@TestMember`

## /welcome

- **Purpose**: Send a welcome message.
- **Arguments (* required)**: member:user
- **Permissions**: Members; Welcome must be enabled in this server.
- **Response**: Public response; errors are private.
- **When disabled**: Disabled features cannot start new actions; see the feature guide for retained data and existing actions.
- **Example**: `/welcome`

## /appeal

- **Purpose**: Open a private modal to appeal your own case.
- **Arguments (* required)**: guild_id*:string, case_id*:integer, application_id:integer
- **Permissions**: The case owner; also available in DMs after leaving the server.
- **Response**: Private response. Managers can inspect DM delivery state for replies and review decisions.
- **When disabled**: New intake, replies and withdrawal are paused while intake is disabled.
- **Example**: `/appeal guild_id:123456789012345678 case_id:1`

## /modmail

- **Purpose**: Start a private inquiry to server managers.
- **Arguments (* required)**: guild_id*:string, application_id:integer
- **Permissions**: Current member of the target server at submission.
- **Response**: Private response. Managers can inspect DM delivery state for replies and review decisions.
- **When disabled**: New intake, replies and withdrawal are paused while intake is disabled.
- **Example**: `/modmail guild_id:123456789012345678`

## /appeal-status

- **Purpose**: Read your own conversations, messages and replies.
- **Arguments (* required)**: guild_id*:string, conversation_id:integer
- **Permissions**: The conversation author only.
- **Response**: Private response. Managers can inspect DM delivery state for replies and review decisions.
- **When disabled**: Authors can still read unexpired conversations.
- **Example**: `/appeal-status guild_id:123456789012345678 conversation_id:1`

## /appeal-reply

- **Purpose**: Reply privately to your own unresolved conversation.
- **Arguments (* required)**: guild_id*:string, conversation_id*:integer
- **Permissions**: The conversation author only.
- **Response**: Private response. Managers can inspect DM delivery state for replies and review decisions.
- **When disabled**: New intake, replies and withdrawal are paused while intake is disabled.
- **Example**: `/appeal-reply guild_id:123456789012345678 conversation_id:1`

## /appeal-withdraw

- **Purpose**: Withdraw your own unresolved conversation.
- **Arguments (* required)**: guild_id*:string, conversation_id*:integer
- **Permissions**: The conversation author only.
- **Response**: Private response. Managers can inspect DM delivery state for replies and review decisions.
- **When disabled**: New intake, replies and withdrawal are paused while intake is disabled.
- **Example**: `/appeal-withdraw guild_id:123456789012345678 conversation_id:1`

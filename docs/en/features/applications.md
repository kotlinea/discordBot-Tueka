---
feature_id: applications
---
# Applications

Collect staff applications, verification requests, partnership proposals or event applications. Answers are private to the applicant's Discord responses and server managers' review screen; they are not published in a channel.

## Prepare a form

Open Applications under Server operations. Enter a title and 1–5 single-line or paragraph questions. Keys start with a lowercase letter and contain up to 40 lowercase letters, digits or underscores, without duplicates. Labels allow 45 characters; answers allow up to 4000. Set required answers and minimum/maximum lengths.

Required roles use any-match rules; denied roles take priority. Leave both lists empty for no role restriction. Set minimum account/membership age and a resubmission cooldown. Choose roles from the server's list. Selected roles that become unavailable remain visible with their IDs so you can correct them before saving.

Enable both the form and Intake settings. Each server can have up to 100 forms. Server management permission is required for configuration and review.

## Submit and check your application

Run `/apply` in Discord and choose an accepting form. Current membership and roles are checked on submission. Reopen the form if its definition changed. One pending/reviewing application is allowed per person per form. Replaying the same submission does not create another application.

`/application-status` privately shows your latest ten applications within retention. To withdraw an open application, provide its number as `withdraw_id`. Final decisions cannot be withdrawn.

## Review

Open Review applications to read the questions as they were at submission time and the answers. Enter a reason and choose Reviewing, Approved or Rejected. Another manager must review your own application. Reviewer, reason and history are recorded together. Approved, rejected and withdrawn are final. Concurrent changes reject the save while preserving your input; discard the reason to review the current version.

## Retention, disabling and recovery

Retention is fixed on submission: 30 days by default, configurable from 1 to 365 days. Expired applications disappear from lists. The Bot deletes up to 500 expired applications, answers and histories per minute, including while intake is disabled. Deletion resumes after a Bot outage. Form definitions and configuration audit remain. Backups have their own retention. Operators who can read the DB or backups can access answers; do not collect passwords or credentials.

To enforce resubmission limits even when the cooldown setting changes, server, form and applicant IDs and the latest submission time are retained for up to 30 days. This record contains no answers or review reasons. Answers and application history are deleted on their configured retention deadline.

Disabling a form stops new submissions. Disabling intake also pauses reviews and withdrawals; managers can still read stored answers until expiry. Retention cleanup continues while disabled.

Forms, applications and histories are included in Tueka's database snapshots. Restore the matching Image and database snapshot together. If a submission response was interrupted, check `/application-status` before submitting again.

(() => {
  const rateTriggers = new Set([
    "message_rate", "duplicate", "mention_rate", "link_rate", "attachment_rate",
    "reaction_rate", "reaction_burst", "join_rate", "leave_rate",
    "new_account_ratio", "emoji_sticker_rate",
  ]);
  const select = document.querySelector("[data-trigger-select]");
  const syncTriggerFields = () => {
    if (!select) return;
    document.querySelectorAll("[data-trigger]").forEach((element) => {
      element.hidden = !element.dataset.trigger.split(",").includes(select.value);
    });
    document.querySelectorAll("[data-rate-trigger]").forEach((element) => {
      element.hidden = !rateTriggers.has(select.value);
    });
  };
  select?.addEventListener("change", syncTriggerFields);
  syncTriggerFields();

  const builder = document.querySelector(".rule-builder");
  if (builder && select) {
    const advanced = builder.querySelector("details .settings-panel");
    const channelOptions = builder.querySelector('[name="condition_channel_ids"]')?.innerHTML || "";
    const roleOptions = builder.querySelector('[name="required_role_ids"]')?.innerHTML || "";
    advanced?.insertAdjacentHTML("beforeend", `
      <label><span>対象カテゴリ</span><select name="condition_category_ids" multiple>${channelOptions}</select></label>
      <label><span>対象ユーザーID</span><textarea name="condition_user_ids"></textarea></label>
      <label><span>除外対象ロール条件</span><select name="excluded_role_ids" multiple>${roleOptions}</select></label>
      <div class="inline-fields"><label><span>最低アカウント年齢（日）</span><input name="minimum_account_age_days" type="number" min="0" max="3650" value="0"></label><label><span>最低参加日数</span><input name="minimum_join_age_days" type="number" min="0" max="3650" value="0"></label></div>
      <label><span>除外カテゴリ</span><select name="exempt_category_ids" multiple>${channelOptions}</select></label>
      <label><span>除外Bot ID</span><textarea name="exempt_bot_ids"></textarea></label>
      <label><span>除外Webhook ID</span><textarea name="exempt_webhook_ids"></textarea></label>
    `);
    builder.querySelector("fieldset")?.insertAdjacentHTML("beforeend", `
      <label><span>公開通知文</span><input name="notify_message" maxlength="500" value="ルール違反を検知しました。"></label>
      <label><span>DM通知文</span><input name="dm_message" maxlength="500" value="ルール違反を検知しました: {reason}"></label>
      <label><span>最近の削除件数</span><input name="purge_count" type="number" min="1" max="100" value="10"></label>
      <label><span>Lockdown対象チャンネル（未指定なら全体）</span><select name="lockdown_channel_ids" multiple>${channelOptions}</select></label>
    `);
    builder.querySelector(".typed-trigger-fields")?.insertAdjacentHTML("beforeend", '<label data-trigger="new_member_activity"><span>参加後の監視時間（分）</span><input name="join_age_minutes" type="number" min="1" max="10080" value="10"></label>');
    const presets = document.createElement("div");
    presets.className = "preset-bar";
    presets.innerHTML = "<strong>用途別プリセット</strong>";
    [...select.options].forEach((option) => {
      const preset = document.createElement("button");
      preset.type = "button";
      preset.className = "secondary";
      preset.textContent = option.textContent;
      preset.addEventListener("click", () => {
        select.value = option.value;
        syncTriggerFields();
        builder.querySelector("[name=name]").value = `${option.textContent} ルール`;
      });
      presets.append(preset);
    });
    builder.querySelector("h2")?.after(presets);

    const preview = document.createElement("button");
    preview.type = "submit";
    preview.className = "secondary";
    preview.textContent = "副作用なしプレビュー";
    preview.formAction = `${location.pathname}/preview`;
    preview.addEventListener("click", () => {
      let input = builder.querySelector("[name=preview_content]");
      if (!input) {
        input = document.createElement("input");
        input.type = "hidden";
        input.name = "preview_content";
        builder.append(input);
      }
      input.value = prompt("テストするメッセージ本文を入力してください。", input.value) || "";
    });
    builder.append(preview);

    const ruleId = new URLSearchParams(location.search).get("rule_id");
    if (ruleId && /^\d+$/.test(ruleId)) {
      fetch(`${location.pathname}/rules/${ruleId}.json`, {headers: {Accept: "application/json"}})
        .then((response) => response.ok ? response.json() : Promise.reject(new Error("rule fetch failed")))
        .then((rule) => {
          const setMany = (name, values) => {
            const input = builder.querySelector(`[name="${name}"]`);
            if (!input) return;
            if (input.tagName === "SELECT") {
              const selected = new Set((values || []).map(String));
              [...input.options].forEach((option) => { option.selected = selected.has(option.value); });
            } else {
              input.value = (values || []).join("\n");
            }
          };
          const conditions = rule.conditions || {};
          const exemptions = rule.exemptions || {};
          [
            ["condition_channel_ids", conditions.channel_ids], ["condition_category_ids", conditions.category_ids],
            ["required_role_ids", conditions.required_role_ids], ["excluded_role_ids", conditions.excluded_role_ids],
            ["condition_user_ids", conditions.user_ids], ["bot_ids", conditions.bot_ids], ["webhook_ids", conditions.webhook_ids],
            ["exempt_channel_ids", exemptions.channel_ids], ["exempt_category_ids", exemptions.category_ids],
            ["exempt_role_ids", exemptions.role_ids], ["exempt_user_ids", exemptions.user_ids],
            ["exempt_bot_ids", exemptions.bot_ids], ["exempt_webhook_ids", exemptions.webhook_ids],
          ].forEach(([name, values]) => setMany(name, values));
          ["minimum_account_age_days", "minimum_join_age_days"].forEach((name) => {
            const input = builder.querySelector(`[name="${name}"]`);
            if (input) input.value = conditions[name] || 0;
          });
          const config = rule.trigger_config || {};
          [["keyword_match", config.match], ["domain_mode", config.mode]].forEach(([name, value]) => {
            const input = builder.querySelector(`[name="${name}"]`);
            if (input && value != null) input.value = value;
          });
          setMany("honeypot_channel_ids", config.channel_ids);
          builder.querySelectorAll('[name="actor_kinds"]').forEach((input) => {
            input.checked = (conditions.actor_kinds || []).includes(input.value);
          });
          for (const action of rule.actions || []) {
            const mapping = {
              points: [["points", action.points], ["expires_days", action.expires_days]],
              timeout: [["duration_minutes", action.duration_minutes]],
              tempban: [["duration_minutes", action.duration_minutes]],
              purge: [["purge_count", action.count]],
              lockdown: [["lockdown_minutes", action.duration_minutes]],
              notify: [["notify_channel_id", action.channel_id], ["notify_message", action.message]],
              dm: [["dm_message", action.message]],
            };
            for (const [name, value] of mapping[action.type] || []) {
              const input = builder.querySelector(`[name="${name}"]`);
              if (input && value != null) input.value = value;
            }
            if (action.type === "lockdown") setMany("lockdown_channel_ids", action.channel_ids);
          }
        })
        .catch(() => {});
    }
  }

  document.querySelectorAll(".rule-card").forEach((card) => {
    const edit = card.querySelector('a[href*="rule_id="]');
    const remove = card.querySelector('form[action$="/delete"]');
    if (!edit || !remove) return;
    const ruleId = new URL(edit.href).searchParams.get("rule_id");
    const duplicate = document.createElement("form");
    duplicate.method = "post";
    duplicate.action = `${location.pathname}/rules/${ruleId}/duplicate`;
    duplicate.innerHTML = `${remove.querySelector('[name=csrf_token]').outerHTML}<button class="secondary" type="submit">複製</button>`;
    remove.before(duplicate);
  });

  const params = new URLSearchParams(location.search);
  if (params.has("preview")) {
    const toast = document.createElement("div");
    toast.className = `toast ${params.get("preview") === "matched" ? "error" : "success"}`;
    toast.textContent = `プレビュー: ${params.get("preview") === "matched" ? "一致" : "不一致"} — ${params.get("preview_reason") || ""}`;
    document.querySelector(".page-header")?.after(toast);
  }

  const list = document.querySelector("[data-threshold-list]");
  document.querySelector("[data-add-threshold]")?.addEventListener("click", () => {
    list?.insertAdjacentHTML("beforeend", '<div class="threshold-row"><input name="threshold_points" type="number" min="1" max="1000" value="3"><select name="threshold_action"><option value="timeout">Timeout</option><option value="kick">Kick</option><option value="ban">Ban</option><option value="tempban">一時Ban</option></select><input name="threshold_duration" type="number" min="1" value="10"><button type="button" data-remove-threshold>×</button></div>');
  });
  document.addEventListener("click", (event) => {
    if (event.target.matches("[data-remove-threshold]")) event.target.closest(".threshold-row")?.remove();
  });
})();

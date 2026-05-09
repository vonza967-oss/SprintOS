from __future__ import annotations

import html
from typing import Any, Iterable


def escape_html(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def preview_text(value: Any, max_length: int = 220) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        return ""
    return text if len(text) <= max_length else text[:max_length].rstrip() + "..."


def render_badge(text: Any, class_name: str = "pill") -> str:
    return f'<span class="{escape_html(class_name)}"><strong>{escape_html(text)}</strong></span>'


def render_button(
    label: Any,
    *,
    onclick: str = "",
    class_name: str = "",
    button_id: str = "",
    disabled: bool = False,
    title: str = "",
) -> str:
    attrs = []
    if button_id:
        attrs.append(f'id="{escape_html(button_id)}"')
    classes = " ".join(part for part in ["button", class_name.strip()] if part).strip()
    if classes:
        attrs.append(f'class="{escape_html(classes)}"')
    if onclick:
        attrs.append(f'onclick="{escape_html(onclick)}"')
    if disabled:
        attrs.append("disabled")
        attrs.append('aria-disabled="true"')
    if title:
        attrs.append(f'title="{escape_html(title)}"')
    attr_text = (" " + " ".join(attrs)) if attrs else ""
    return f"<button{attr_text}>{escape_html(label)}</button>"


def render_copy_button(
    copy_text: Any,
    *,
    button_id: str = "",
    label: str = "Copy",
    class_name: str = "secondary mini",
) -> str:
    attrs = [f'data-copy-text="{escape_html(copy_text)}"']
    if button_id:
        attrs.append(f'id="{escape_html(button_id)}"')
    if class_name:
        attrs.append(f'class="{escape_html(class_name)}"')
    return f"<button {' '.join(attrs)}>{escape_html(label)}</button>"


def render_status_label(status: Any) -> str:
    normalized = str(status or "info").strip().lower() or "info"
    return f'<span class="status-badge {escape_html(normalized)}">{escape_html(normalized)}</span>'


def render_issue_lines(items: Iterable[Any], kind: str) -> str:
    return "".join(
        f'<div class="muted"><strong>{escape_html(kind)}:</strong> {escape_html(item)}</div>'
        for item in items
    )


def render_card(body: Any, class_name: str = "resume-plan") -> str:
    return f'<div class="{escape_html(class_name)}">{body}</div>'


def render_empty_state(text: Any, class_name: str = "muted") -> str:
    return f'<p class="{escape_html(class_name)}">{escape_html(text)}</p>'


def render_section_header(title: Any, subtitle: Any = "") -> str:
    return (
        '<div class="section-group-header">'
        f"<div><h3 style=\"margin:0\">{escape_html(title)}</h3>"
        f"<p class=\"muted\">{escape_html(subtitle)}</p></div>"
        "</div>"
    )


def render_project_section(
    section_id: Any,
    title: Any,
    subtitle: Any,
    body: Any,
    *,
    open: bool,
    badge_text: Any = "",
) -> str:
    badge_html = render_badge(badge_text) if str(badge_text or "").strip() else ""
    toggle_label = "Collapse" if open else "Expand"
    collapsed_class = "" if open else " is-collapsed"
    return (
        f'<section id="section-{escape_html(section_id)}" class="section-group{collapsed_class}">'
        '<div class="section-group-header">'
        f"<div><h3 style=\"margin:0\">{escape_html(title)}</h3>"
        f"<p class=\"muted\">{escape_html(subtitle)}</p></div>"
        '<div class="section-group-actions">'
        f"{badge_html}"
        f'<button class="secondary mini" data-role="section-toggle" aria-expanded="{str(open).lower()}" '
        f'onclick="toggleProjectSection(\'{escape_html(section_id)}\')">{toggle_label}</button>'
        "</div></div>"
        f'<div class="section-body">{body}</div>'
        "</section>"
    )


def render_copyable_text_block(
    *,
    element_id: str,
    title: str,
    text: Any,
    empty_text: str = "No saved text yet.",
    copy_action: str = "",
    open_url: str = "",
    open_by_default: bool = False,
    preview_length: int = 240,
) -> str:
    normalized_text = str(text or "").strip()
    if not normalized_text:
        return render_card(render_empty_state(empty_text))
    actions = []
    if copy_action:
        actions.append(
            f'<button class="secondary mini" onclick="{escape_html(copy_action)}(this)">Copy</button>'
        )
    if open_url:
        actions.append(
            f'<a class="button-link secondary mini" href="{escape_html(open_url)}" target="_blank" rel="noopener">Open report</a>'
        )
    actions_html = f'<div class="text-block-actions">{"".join(actions)}</div>' if actions else ""
    disclosure = "Expand" if len(normalized_text) > preview_length else "View"
    open_attr = " open" if open_by_default else ""
    return (
        f'<details class="text-block"{open_attr}>'
        "<summary><div>"
        f"<strong>{escape_html(title)}</strong>"
        f'<div class="preview-copy">{escape_html(preview_text(normalized_text, preview_length))}</div>'
        f'</div><span class="tiny-badge">{disclosure}</span></summary>'
        f"{actions_html}"
        f'<pre id="{escape_html(element_id)}">{escape_html(normalized_text)}</pre>'
        "</details>"
    )


UI_HELPERS_JS = """
function esc(value) {
  return String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',\"'\":'&#39;','\"':'&quot;'}[c]));
}

function buttonDisabledAttr(disabled, reason = '') {
  return disabled ? `disabled title="${esc(reason || 'This action is not available yet.')}" aria-disabled="true"` : '';
}

function previewText(value, maxLength = 220) {
  const text = String(value || '').replace(/\\s+/g, ' ').trim();
  if (!text) return '';
  return text.length <= maxLength ? text : text.slice(0, maxLength).trim() + '…';
}

function renderCopyableTextBlock(config) {
  const text = String(config.text || '').trim();
  if (!text) {
    return `<div class="resume-plan"><p class="muted">${esc(config.emptyText || 'No saved text yet.')}</p></div>`;
  }
  const actions = [];
  if (config.copyAction) {
    actions.push(`<button class="secondary mini" onclick="${esc(config.copyAction)}(this)">Copy</button>`);
  }
  if (config.openUrl) {
    actions.push(`<a class="button-link secondary mini" href="${esc(config.openUrl)}" target="_blank" rel="noopener">Open report</a>`);
  }
  return `
    <details class="text-block"${config.open ? ' open' : ''}>
      <summary>
        <div>
          <strong>${esc(config.title || 'Saved text')}</strong>
          <div class="preview-copy">${esc(previewText(text, config.previewLength || 240))}</div>
        </div>
        <span class="tiny-badge">${text.length > (config.previewLength || 240) ? 'Expand' : 'View'}</span>
      </summary>
      ${actions.length ? `<div class="text-block-actions">${actions.join('')}</div>` : ''}
      <pre id="${esc(config.id)}">${esc(text)}</pre>
    </details>
  `;
}

function renderIssueLines(items, kind) {
  return (items || []).map(item => `<div class="muted"><strong>${esc(kind)}:</strong> ${esc(item)}</div>`).join('');
}

function renderDetailsBlock(summary, bodyHtml, note = '') {
  if (!bodyHtml || !String(bodyHtml).trim()) return '';
  return `
    <details class="support-details" style="margin-top:12px">
      <summary>
        <strong>${esc(summary || 'Details')}</strong>
        ${note ? `<span class="button-label-muted">${esc(note)}</span>` : ''}
      </summary>
      <div style="margin-top:12px">${bodyHtml}</div>
    </details>
  `;
}

function renderTinyBadges(badges) {
  return (badges || []).map((badge) => `<span class="tiny-badge">${esc(badge.label || badge.id || '')}</span>`).join('');
}

function renderTodayProjectItem(item) {
  if (!item) return '';
  return `
    <div class="today-item" onclick="openProject('${esc(item.project_id || '')}')">
      <div class="today-item-head">
        <strong>${esc(item.project_title || '')}</strong>
        <span class="pill"><strong>${esc(item.stage_label || item.stage || item.status || '')}</strong></span>
      </div>
      ${item.badges && item.badges.length ? `<div class="project-badges" style="margin-bottom:6px">${renderTinyBadges(item.badges)}</div>` : ''}
      <div class="muted">${esc(item.headline_issue || item.next_tiny_action || '')}</div>
    </div>
  `;
}

function renderTodayProjectList(items, emptyText) {
  if (!items || !items.length) return `<div class="muted">${esc(emptyText)}</div>`;
  return `<div class="today-list">${items.map(renderTodayProjectItem).join('')}</div>`;
}

function renderStatusBadge(status) {
  const value = String(status || 'info').toLowerCase();
  return `<span class="status-badge ${esc(value)}">${esc(value)}</span>`;
}

function renderActivityItem(event, options = {}) {
  const showProject = !!options.showProject;
  if (!event) return '';
  const projectLine = showProject && event.project_title
    ? `<div class="muted">${esc(event.project_title)}</div>`
    : '';
  const reportLink = event.report_url
    ? `<a href="${esc(event.report_url)}">Open report</a>`
    : '';
  return `
    <div class="activity-item">
      <div class="activity-item-head">
        <div>
          ${projectLine}
          <strong>${esc(event.title || '')}</strong>
        </div>
        ${renderStatusBadge(event.event_status)}
      </div>
      <div class="muted">${esc(event.summary || '')}</div>
      ${event.next_tiny_action ? `<div class="activity-meta"><strong>Next tiny action:</strong> ${esc(event.next_tiny_action)}</div>` : ''}
      <div class="activity-meta">${esc(event.created_at || '')}${reportLink ? ' · ' + reportLink : ''}</div>
    </div>
  `;
}

function renderActivityList(events, emptyText, options = {}) {
  if (!events || !events.length) return `<div class="muted">${esc(emptyText)}</div>`;
  return `<div class="activity-list">${events.map((event) => renderActivityItem(event, options)).join('')}</div>`;
}

function renderProjectSection(sectionId, title, subtitle, body, open, badgeText = '') {
  return `
    <section id="section-${esc(sectionId)}" class="section-group ${open ? '' : 'is-collapsed'}">
      <div class="section-group-header">
        <div>
          <h3 style="margin:0">${esc(title)}</h3>
          <p class="muted">${esc(subtitle || '')}</p>
        </div>
        <div class="section-group-actions">
          ${badgeText ? `<span class="pill"><strong>${esc(badgeText)}</strong></span>` : ''}
          <button class="secondary mini" data-role="section-toggle" aria-expanded="${open ? 'true' : 'false'}" onclick="toggleProjectSection('${esc(sectionId)}')">${open ? 'Collapse' : 'Expand'}</button>
        </div>
      </div>
      <div class="section-body">${body}</div>
    </section>
  `;
}
""".strip()

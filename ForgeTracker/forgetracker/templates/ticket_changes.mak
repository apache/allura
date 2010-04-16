% for key, values in changelist:
% if key == 'description':
  description has changed
% else:
<% oldv, newv = values %>
% if key == 'assigned_to':
    <% oldv = oldv.display_name %>
    <% newv = newv.display_name %>
% endif
% if key == 'labels':
    <% oldv = ', '.join(oldv.display_name) %>
    <% newv = ', '.join(newv.display_name) %>
% endif
- **${key}**: ${oldv} → ${newv}
% endif
% endfor

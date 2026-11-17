---
name: edit-magento-cms-page-title
description: Update the title of a named CMS page in Magento Admin and verify the save confirmation.
version: 1
params:
  existing_title:
    type: string
    description: Current title of the CMS page to edit.
  replacement_title:
    type: string
    description: New title to assign to the CMS page.
url_pattern: ^/
required_elements: []
preconditions: []
time_limit_s: 120.0
---

1. Open the observed CMS page list at `/cms/page/`; check that the Pages heading appears.
2. In the table row containing `existing_title`, click its Select button; check that an Edit link is shown in that same row.
3. Click Edit in that row; check that the page is an edit form and that the Page Title * textbox is present.
4. Replace the Page Title * field with `replacement_title`; check that the new title is shown.
5. Click Save; check for the “You saved the page.” confirmation and the heading `replacement_title`.

Pitfalls:
- Use the Select and Edit controls in the row for the requested page, not another page's controls.
- Click Save, not Save options.
- Confirm the save message before treating the change as complete.

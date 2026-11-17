---
name: change-cms-page-title
description: Change the title of a selected Magento CMS page and verify the saved result.
version: 1
params:
  old_heading:
    type: string
    description: The current title of the CMS page to edit.
  heading:
    type: string
    description: The new title to set for that CMS page.
url_pattern: ^/
required_elements: []
preconditions: []
time_limit_s: 120.0
---

1. Open the CMS Pages grid at `/cms/page/` and check that the Pages heading is shown.
2. In the grid, identify the row whose Title is exactly `old_heading`. Click that row's `Select` button, then check that its `Edit` link is visible in the same row.
3. Click `Edit` in that row and check that the `Page Title *` textbox is present.
4. Replace the `Page Title *` value with `heading` and check that the new title is displayed on the form.
5. Click `Save` and check for the confirmation `You saved the page.`

Pitfalls: The row's `Select` button opens row actions; it does not edit the page by itself. Be sure to choose `Edit` in the row matching `old_heading`, not a neighboring CMS page. Verify the save confirmation before finishing.

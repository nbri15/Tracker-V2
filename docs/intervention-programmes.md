# Intervention programme library

School admins open **Interventions → Manage programme library**, then add a name,
subject and optional guidance. Programmes belong to the selected school. Their
subject cannot be changed after creation; archive an old programme and create a
new one instead. Archiving blocks new assignments and preserves existing ones.

Teachers choose the academic year, term and subject on **Interventions**. They can:

- Assign an existing pupil using their programme menu, or drag an intervention
  row into a programme card. The menu works on touch screens and with a keyboard.
- Use **Add pupil / programme** for any active pupil in their assigned class,
  including pupils outside the automatic suggestion list.
- Assign a pupil to several programmes without duplicating the same assignment.
- Expand **View / edit plan** to edit notes. A separate saved/error message is
  shown for each plan; Save plan remains available. Pending saves finish before
  programme assignment, filtering or navigation.
- Dismiss an active automatic suggestion with the × in its top-right corner,
  provided no programme is assigned. It moves to Closed, preserves marks and
  notes, and will not automatically reappear on assessment updates. Reopen it
  from Closed if needed. Assigned programmes and manual support keep their
  explicit Close intervention action.
- Close and reopen support explicitly. Closed notes and programme assignments
  remain available in the Closed tab for the selected academic year and term.

The automatic rule still suggests up to six pupils below their saved pass
threshold, now ordered by the actual percentage-point gap. Programmes assigned
by teachers are not automatically closed when assessment results change.
Closing an intervention is respected on later result/configuration saves.
Exact-term assessment scores are shown; a missing score does not borrow from
another term, and zero remains zero. This is assessment context, not a claim
that a programme has caused progress or an intervention-specific pre/post test.

The admin overview offers term and programme filters, with the same scope
applied to screen, PDF, print and CSV. Programmes are included in exports.

## Deployment and preservation

Apply `flask db upgrade` through the existing deployment migration process
before starting this application version. Revision `20261030_01` follows
`20261021_01`. It adds the programme and assignment tables and a teacher-closure
flag. Existing assessments, pupil marks, intervention reasons and notes are not
rewritten. Existing inactive interventions remain closed until explicitly
reopened. Existing active interventions stay active and start without a
programme; staff can assign them without re-entering their plans.

There are no built-in programmes, automatic assignments, destructive resets or
changes to Maths Fundamentals. The feature uses school/class access boundaries
and CSRF protection. Programme assignments are removed with a permanently
deleted pupil or school; otherwise archiving preserves support records.

Regression tests use fictional SQLite fixtures, the actual additive migration
against SQLite and a disposable PostgreSQL 17 CI service, and browser checks for
menu assignment, drag/drop, responsive layout, pending notes and admin creation.
No production database is used in tests.

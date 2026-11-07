-- Deleting resume versions.
--
-- The person can delete a version of a resume, or a version and every one
-- after it, and with its last version the resume itself. Deleting erases a
-- version's content and the names given to it. The row, its number, date and
-- hashes stay, so later versions keep their whole pages and the chain still
-- verifies. resume_version_immutable (0007) already allows exactly this
-- change and no other; until now the app had no grant to make it.
--
-- A deleted resume is archived, and its name blanked (re-encrypted empty),
-- with the grants it already had.

grant update (content_ciphertext, redacted_at) on plytos.resume_version to plytos_app;
grant delete on plytos.resume_version_name to plytos_app;

-- What a reading holds, in numbers: how many cards it proposes and which of
-- its findings the person settles. Encrypted like the reading itself. Listing
-- a person's files reads this instead of opening every reading, which can be
-- large and slow to fetch from a far database.
--
-- Written with the reading. Imports read before this get theirs the first time
-- they're listed; it is only ever filled in, never changed.

alter table plytos.resume_import add column outline_ciphertext bytea;

grant update (outline_ciphertext) on plytos.resume_import to plytos_app;

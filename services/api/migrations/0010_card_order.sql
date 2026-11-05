-- The order the person puts cards in among their siblings: the titles under
-- an employment, the accomplishments under a title, or the cards in a section
-- of their library. Null sorts after every placed card, oldest first. The
-- order holds no card text, so it sits in the clear like parent_id.
alter table plytos.card add column sort_key integer;

grant update (sort_key) on plytos.card to plytos_app;

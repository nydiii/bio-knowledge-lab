from bio_knowledge_lab.extraction import ground_entities,ground_relations

def test_grounding_exact_not_substring_and_no_gold():
    doc={"text":"IL6 and IL6R; IL6."}
    entities,issues=ground_entities(doc,{"entities":[{"text":"IL6","type":"GeneOrGeneProduct"}]})
    assert [e["start"] for e in entities]==[0,14]
    assert not issues
    assert all("ids" not in e for e in entities)

def test_string_evidence_not_split_into_characters():
    doc={"text":"A binds B"}
    entities=[{"mention_id":"m1"},{"mention_id":"m2"}]
    relations,issues=ground_relations(doc,entities,{"relations":[{
        "head":"m1","tail":"m2","type":"Bind","evidence":"A binds B"}]})
    assert relations[0]["evidence"]==[]
    assert issues[0]["kind"]=="invalid_evidence_list"

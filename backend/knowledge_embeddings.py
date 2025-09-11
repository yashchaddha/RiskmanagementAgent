import os
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings
from pymilvus import (
    connections, utility,
    FieldSchema, CollectionSchema, DataType, Collection
)
from knowledge_base import ISO_27001_KNOWLEDGE

load_dotenv()

HEAD_BY_TYPE = {
    "clause": "ISO 27001 clause",
    "subclause": "ISO 27001 subclause", 
    "domain": "ISO 27001 Annex A domain",
    "control": "ISO 27001 control",
}

def convert_to_natural_language(doc_data, doc_type):
    """Create a natural, flowing sentence without colons."""
    id_ = (doc_data.get("id") or "").strip()
    title = (doc_data.get("title") or "").strip()
    desc = (doc_data.get("description") or "").strip()
    head = HEAD_BY_TYPE.get(doc_type, "").strip()

    if head and id_ and title and desc:
        text = f"{head} {id_} is titled '{title}'. {desc}"
    elif head and id_ and title:
        text = f"{head} {id_} is titled '{title}'."
    elif head and id_ and desc:
        text = f"{head} {id_} covers the following: {desc}"
    elif head and title and desc:
        text = f"{head} titled '{title}' covers: {desc}"
    elif head and id_:
        text = f"{head} {id_}."
    elif title and desc:
        text = f"'{title}': {desc}"
    elif title:
        text = f"'{title}'."
    elif desc:
        text = desc
    else:
        text = f"{head} {id_}".strip() or "Information security content."
    
    text = text.strip()
    if text and not text.endswith(('.', '!', '?')):
        text += '.'
    
    return text

def main():
    print("Starting simple knowledge base embedding process...")
    
    embeddings_model = OpenAIEmbeddings(model="text-embedding-3-small")
    connections.connect(
        alias="default",
        uri=os.getenv("ZILLIZ_URI"),
        token=os.getenv("ZILLIZ_TOKEN"),
        db_name=os.getenv("ZILLIZ_DB", "default"),
        timeout=30,
    )
    
    collection_name = "iso_knowledge_index"
    
    if utility.has_collection(collection_name):
        utility.drop_collection(collection_name)
        print("Dropped existing collection")

    fields = [
        FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=False),
        FieldSchema(name="doc_id", dtype=DataType.VARCHAR, max_length=64),
        FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=4096),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=1536),
    ]
    schema = CollectionSchema(fields=fields, description="ISO 27001 Knowledge Base semantic index")

    collection = Collection(name=collection_name, schema=schema, using="default")

    index_params = {
        "index_type": "IVF_FLAT",
        "metric_type": "COSINE",
        "params": {"nlist": 1024},
    }
    collection.create_index(field_name="embedding", index_params=index_params)

    collection.load()
    print("Created and loaded new collection")
    
    knowledge = ISO_27001_KNOWLEDGE["ISO27001_2022"]
    doc_count = 0
    
    for clause in knowledge["Clauses"]:
        text = convert_to_natural_language(clause, "clause")
        embedding = embeddings_model.embed_query(text)
        
        data = [
            [doc_count],
            [clause["id"]],
            [text],
            [embedding],
        ]
        collection.insert(data)
        print(f"Inserted clause {clause['id']}")
        doc_count += 1
        
        for subclause in clause.get("subclauses", []):
            text = convert_to_natural_language(subclause, "subclause")
            embedding = embeddings_model.embed_query(text)
            
            data = [
                [doc_count],
                [subclause["id"]],
                [text],
                [embedding],
            ]
            collection.insert(data)
            print(f"Inserted subclause {subclause['id']}")
            doc_count += 1
    
    for domain in knowledge["Annex_A"]:
        text = convert_to_natural_language(domain, "domain")
        embedding = embeddings_model.embed_query(text)
        
        data = [
            [doc_count],
            [domain["id"]],
            [text],
            [embedding],
        ]
        collection.insert(data)
        print(f"Inserted domain {domain['id']}")
        doc_count += 1
        
        for control in domain.get("controls", []):
            text = convert_to_natural_language(control, "control")
            embedding = embeddings_model.embed_query(text)
            
            data = [
                [doc_count],
                [control["id"]],
                [text],
                [embedding],
            ]
            collection.insert(data)
            print(f"Inserted control {control['id']}")
            doc_count += 1
    
    collection.flush()
    print(f"SUCCESS: Processed {doc_count} documents")

if __name__ == "__main__":
    main()
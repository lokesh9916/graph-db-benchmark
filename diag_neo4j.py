from neo4j import GraphDatabase
import os
from dotenv import load_dotenv

load_dotenv()
user = os.environ.get('NEO4J_USERNAME') or os.environ.get('NEO4J_USER', 'neo4j')
pw = os.environ['NEO4J_PASSWORD']

# Try the routing endpoint and the direct member address from SHOW DATABASES
uris = [
    os.environ['NEO4J_URI'],
    'bolt+ssc://p-mt-3b814dd7cab7-12-0101.production-orch-0068.neo4j.io:7687',
]

for uri in uris:
    print(f'\n=== URI={uri} ===')
    try:
        driver = GraphDatabase.driver(uri, auth=(user, pw))
        driver.verify_connectivity()
        print('connected')
        with driver.session(database='10a55cb8') as s:
            print('RETURN:', s.run('RETURN 1 AS n').single()['n'])
        driver.close()
    except Exception as e:
        print(type(e).__name__, str(e)[:300])

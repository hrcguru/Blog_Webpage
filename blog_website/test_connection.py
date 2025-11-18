from pymongo import MongoClient
import urllib.parse

username = "hritikmasai_db_user"
password = "Adinath7"
cluster_url = "blogging.blekm0p.mongodb.net"

MONGODB_URI = f"mongodb+srv://{urllib.parse.quote_plus(username)}:{urllib.parse.quote_plus(password)}@{cluster_url}/?retryWrites=true&w=majority"

try:
    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=10000)
    
    # List all databases
    databases = client.list_database_names()
    print("✅ Connected successfully!")
    print("📊 Available databases:", databases)
    
    # Test with each database
    for db_name in databases:
        try:
            db = client[db_name]
            db.command('ping')
            print(f"✅ Database '{db_name}' is accessible")
        except:
            print(f"❌ Database '{db_name}' not accessible")
            
except Exception as e:
    print(f"❌ Connection failed: {e}")
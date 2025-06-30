DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'agent_metrics_db',
    'username': 'postgres',
    'password': 'postgres'
}

DATABASE_URL = f"postgresql://{DB_CONFIG['username']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
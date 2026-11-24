"""Demo data:  python -m app.seed   (password for all demo users: Demo@12345)"""
from .db import Base, engine, SessionLocal
from .models import *
from .security import hash_password

def seed(db):
    pw = hash_password("Demo@12345")
    org, other = Organization(name="Sharma & Co. CAs"), Organization(name="Other CA Firm")
    db.add_all([org, other]); db.flush()
    cl = Client(organization_id=org.id, client_name="Acme Traders Pvt Ltd"); db.add(cl); db.flush()
    g = ClientGstin(organization_id=org.id, client_id=cl.id, gstin="36ABCDE1234F1Z5", registered_mobile_label="Owner phone ••••21"); db.add(g)
    mk = lambda o, n, e, r, c=None: User(organization_id=o.id, name=n, email=e, role=r, client_id=c, password_hash=pw)
    users = [mk(org, "Admin", "admin@sharma.co.in", "ADMIN"), mk(org, "Anita Auditor", "auditor@sharma.co.in", "AUDITOR"),
             mk(org, "Raj (Acme)", "client@acme.co.in", "CLIENT", cl.id), mk(other, "Mallory", "auditor@otherca.co.in", "AUDITOR")]
    db.add_all(users); db.commit()
    return {"org": org.id, "client": cl.id, "gstin": g.id}

if __name__ == "__main__":
    Base.metadata.create_all(engine)
    with SessionLocal() as db: print(seed(db))


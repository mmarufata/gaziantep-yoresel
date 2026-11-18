"""
Veritabanı migration scripti - Order tablosuna yeni kolonlar ekler
"""
import secrets
from app import app, db, Product
from sqlalchemy import text

with app.app_context():
    try:
        db.create_all()
        print("[OK] Eksik tablolar oluşturuldu (payment dahil).")
        shipment_result = db.session.execute(
            text(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='shipment'"
            )
        )
        if shipment_result.fetchone():
            print("[OK] shipment tablosu mevcut")
        else:
            print("[HATA] shipment tablosu oluşturulamadı")
        # Mevcut kolonları kontrol et
        result = db.session.execute(text("PRAGMA table_info('order')"))
        columns = [row[1] for row in result]
        
        print("Mevcut kolonlar:", columns)
        
        # Eksik kolonları ekle
        if 'order_number' not in columns:
            print("order_number kolonu ekleniyor...")
            db.session.execute(text("ALTER TABLE `order` ADD COLUMN order_number VARCHAR(50)"))
            db.session.commit()
            print("[OK] order_number eklendi")
        
        if 'payment_status' not in columns:
            print("payment_status kolonu ekleniyor...")
            db.session.execute(text("ALTER TABLE `order` ADD COLUMN payment_status VARCHAR(50) DEFAULT 'Beklemede'"))
            db.session.commit()
            print("[OK] payment_status eklendi")
        
        if 'total_amount' not in columns:
            print("total_amount kolonu ekleniyor...")
            db.session.execute(text("ALTER TABLE `order` ADD COLUMN total_amount FLOAT"))
            db.session.commit()
            print("[OK] total_amount eklendi")
        
        if 'shipping_cost' not in columns:
            print("shipping_cost kolonu ekleniyor...")
            db.session.execute(text("ALTER TABLE `order` ADD COLUMN shipping_cost FLOAT DEFAULT 0.0"))
            db.session.commit()
            print("[OK] shipping_cost eklendi")
        
        if 'transaction_id' not in columns:
            print("transaction_id kolonu ekleniyor...")
            db.session.execute(text("ALTER TABLE `order` ADD COLUMN transaction_id VARCHAR(100)"))
            db.session.commit()
            print("[OK] transaction_id eklendi")
        
        if 'city' not in columns:
            print("city kolonu ekleniyor...")
            db.session.execute(text("ALTER TABLE `order` ADD COLUMN city VARCHAR(100)"))
            db.session.commit()
            print("[OK] city eklendi")
        
        if 'district' not in columns:
            print("district kolonu ekleniyor...")
            db.session.execute(text("ALTER TABLE `order` ADD COLUMN district VARCHAR(100)"))
            db.session.commit()
            print("[OK] district eklendi")
        
        if 'neighborhood' not in columns:
            print("neighborhood kolonu ekleniyor...")
            db.session.execute(text("ALTER TABLE `order` ADD COLUMN neighborhood VARCHAR(100)"))
            db.session.commit()
            print("[OK] neighborhood eklendi")

        if 'email' not in columns:
            print("email kolonu ekleniyor...")
            db.session.execute(text("ALTER TABLE `order` ADD COLUMN email VARCHAR(120)"))
            db.session.commit()
            print("[OK] email eklendi")

        if 'notify_sms' not in columns:
            print("notify_sms kolonu ekleniyor...")
            db.session.execute(text("ALTER TABLE `order` ADD COLUMN notify_sms BOOLEAN DEFAULT 1"))
            db.session.commit()
            print("[OK] notify_sms eklendi")

        if 'notify_email' not in columns:
            print("notify_email kolonu ekleniyor...")
            db.session.execute(text("ALTER TABLE `order` ADD COLUMN notify_email BOOLEAN DEFAULT 1"))
            db.session.commit()
            print("[OK] notify_email eklendi")

        if 'cargo_company' not in columns:
            print("cargo_company kolonu ekleniyor...")
            db.session.execute(text("ALTER TABLE `order` ADD COLUMN cargo_company VARCHAR(100)"))
            db.session.commit()
            print("[OK] cargo_company eklendi")

        if 'cargo_tracking_no' not in columns:
            print("cargo_tracking_no kolonu ekleniyor...")
            db.session.execute(text("ALTER TABLE `order` ADD COLUMN cargo_tracking_no VARCHAR(100)"))
            db.session.commit()
            print("[OK] cargo_tracking_no eklendi")

        if 'cargo_tracking_url' not in columns:
            print("cargo_tracking_url kolonu ekleniyor...")
            db.session.execute(text("ALTER TABLE `order` ADD COLUMN cargo_tracking_url VARCHAR(255)"))
            db.session.commit()
            print("[OK] cargo_tracking_url eklendi")
        
        if 'public_token' not in columns:
            print("public_token kolonu ekleniyor...")
            db.session.execute(
                text("ALTER TABLE `order` " "ADD COLUMN public_token VARCHAR(64)")
            )
            db.session.commit()
            print("[OK] public_token eklendi")
        
        if 'admin_hidden' not in columns:
            print("admin_hidden kolonu ekleniyor...")
            db.session.execute(
                text("ALTER TABLE `order` ADD COLUMN admin_hidden BOOLEAN NOT NULL DEFAULT 0")
            )
            db.session.commit()
            print("[OK] admin_hidden eklendi")

        # Mevcut siparişlere order_number atama (eğer varsa)
        from app import Order
        orders_without_number = Order.query.filter(Order.order_number == None).all()
        if orders_without_number:
            from app import _generate_order_number
            for order in orders_without_number:
                order_number = _generate_order_number()
                # Benzersizlik kontrolü
                while Order.query.filter_by(order_number=order_number).first():
                    order_number = _generate_order_number()
                order.order_number = order_number
                if not order.total_amount:
                    order.total_amount = order.total if hasattr(order, 'total') else 0.0
            db.session.commit()
            print(f"[OK] {len(orders_without_number)} siparişe order_number atandı")
        db.session.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "ix_order_order_number "
                "ON `order` (order_number)"
            )
        )
        db.session.commit()
        print("[OK] order_number benzersiz indeksi kontrol edildi")

        try:
            result = db.session.execute(text("PRAGMA table_info('comment')"))
            comment_cols = [row[1] for row in result]
        except Exception:
            comment_cols = []

        if comment_cols and "user_id" in comment_cols:
            has_author_col = "author_name" in comment_cols
            if has_author_col:
                author_expr = """COALESCE(
                    NULLIF(TRIM(COALESCE(c.author_name, '')), ''),
                    (SELECT u.username FROM user u WHERE u.id = c.user_id),
                    'Misafir'
                )"""
            else:
                author_expr = """COALESCE(
                    (SELECT u.username FROM user u WHERE u.id = c.user_id),
                    'Misafir'
                )"""
            print("comment tablosu yeniden olusturuluyor (user_id -> author_name)...")
            db.session.execute(
                text("DROP TABLE IF EXISTS comment_mig")
            )
            db.session.execute(
                text(
                    """
                    CREATE TABLE comment_mig (
                        id INTEGER NOT NULL PRIMARY KEY,
                        product_id INTEGER NOT NULL,
                        author_name VARCHAR(80) NOT NULL,
                        content TEXT NOT NULL,
                        created_at DATETIME,
                        FOREIGN KEY(product_id) REFERENCES product (id)
                    )
                    """
                )
            )
            db.session.execute(
                text(
                    f"""
                    INSERT INTO comment_mig (id, product_id, author_name, content, created_at)
                    SELECT c.id, c.product_id, {author_expr}, c.content, c.created_at
                    FROM comment c
                    """
                )
            )
            db.session.execute(text("DROP TABLE comment"))
            db.session.execute(text("ALTER TABLE comment_mig RENAME TO comment"))
            db.session.commit()
            print("[OK] comment tablosu guncellendi")

        try:
            result = db.session.execute(text("PRAGMA table_info('product')"))
            product_cols = [row[1] for row in result]
        except Exception:
            product_cols = []

        if product_cols and "description" not in product_cols:
            print("product.description kolonu ekleniyor...")
            db.session.execute(text("ALTER TABLE product ADD COLUMN description TEXT"))
            db.session.commit()
            print("[OK] product.description eklendi")

        if product_cols and "display_order" not in product_cols:
            print("product.display_order kolonu ekleniyor...")
            db.session.execute(text("ALTER TABLE product ADD COLUMN display_order INTEGER NOT NULL DEFAULT 0"))
            db.session.commit()
            db.session.execute(text("UPDATE product SET display_order = id * 10 WHERE display_order = 0 OR display_order IS NULL"))
            db.session.commit()
            print("[OK] product.display_order eklendi")

        if product_cols and "gramaj_options" not in product_cols:
            print("product.gramaj_options kolonu ekleniyor...")
            db.session.execute(text("ALTER TABLE product ADD COLUMN gramaj_options VARCHAR(100)"))
            db.session.commit()
            db.session.execute(
                text("UPDATE product SET gramaj_options = '100,500,1000' WHERE unit = 'Kg' AND (gramaj_options IS NULL OR gramaj_options = '')")
            )
            db.session.commit()
            print("[OK] product.gramaj_options eklendi")

        if product_cols and "image2" not in product_cols:
            print("product.image2 kolonu ekleniyor...")
            db.session.execute(text("ALTER TABLE product ADD COLUMN image2 VARCHAR(200)"))
            db.session.commit()
            print("[OK] product.image2 eklendi")

        if product_cols and "video" not in product_cols:
            print("product.video kolonu ekleniyor...")
            db.session.execute(text("ALTER TABLE product ADD COLUMN video VARCHAR(200)"))
            db.session.commit()
            print("[OK] product.video eklendi")
            
        db.session.commit()

        print("\n[OK] Veritabani migration tamamlandi!")
        
    except Exception as e:
        print(f"[HATA] {e}")
        db.session.rollback()
# seed.py
from app import db, Product, app

with app.app_context():
    db.drop_all()  
    db.create_all()

    products = [
        ("Kimyon", "Baharat", 300, "Kg"),
        ("Sumak", "Baharat", 250, "Kg"),
        ("Kahvaltılık zahter ", "Baharat", 40, "250 Gr"),
        ("Haspir", "Baharat", 700, "Kg"),
        ("İsot", "Baharat", 250, "Kg"),
        ("Kuru zencefil", "Baharat", 250, "Kg"),
        ("Zerdeçal", "Baharat", 250, "Kg"),
        ("Karabiber", "Baharat", 500, "Kg"),
        ("Kekik", "Baharat", 300, "Kg"),
        ("Nane", "Baharat", 250, "Kg"),
        ("Köfte baharatı", "Baharat", 300, "Kg"),
        ("Limon tuzu (iri)", "Baharat", 135, "Kg"),
        ("Limon tuzu (ufak)", "Baharat", 125, "Kg"),
        ("Mahlep", "Baharat", 800, "Kg"),
        ("Kendir tohumu", "Baharat", 250, "Kg"),
        ("Köri", "Baharat", 150, "Kg"),
        ("Türk kahvesi", "Baharat", 500, "Kg"),
        ("Granül kahve", "Baharat", 750, "Kg"),
        ("Süt tozu", "Baharat", 150, "Kg"),
        ("Menengiç kahvesi ", "Baharat", 45, "150 Gr"),
        ("Çay", "İçecek", 85, "100 Gr"),

        ("İpek Biber", "Pul Biber", 300, "Kg"),
        ("Toz Biber", "Pul Biber", 250, "Kg"),
        ("Dövme Biber", "Pul Biber", 250, "Kg"),

        ("Patlıcan Kurusu", "Kuruluk", 190, "Adet"),
        ("Acı Biber Kurusu", "Kuruluk", 140, "Adet"),
        ("Tatlı Biber Kurusu", "Kuruluk", 150, "Adet"),
        ("Acur Kurusu", "Kuruluk", 190, "Adet"),
        ("Kabak Kurusu", "Kuruluk", 250, "Adet"),

        ("Domates Salçası", "Salça", 125, "Kg"),
        ("Gün Salçası", "Salça", 225, "Kg"),
        ("Tatlı Salça", "Salça", 175, "Kg"),
        ("Acı Salça", "Salça", 175, "Kg"),

        ("Firik", "Hububat", 130, "Kg"),
        ("Dövme", "Hububat", 35, "Kg"),
        ("Maraş Tarhanası (çorbalık)", "Hububat", 225, "Kg"),
        ("Maraş Tarhanası (kırık)", "Hububat", 175, "Kg"),
        ("Çerezlik Tarhana (500 Gr)", "Hububat", 150, "500 Gr"),

        ("Antep Fıstığı", "Kuruyemiş", 1200, "Kg"),
        ("Kuru Üzüm (çekirdekli siyah)", "Kuruyemiş", 280, "Kg"),
        ("Kuru Üzüm (Besni)", "Kuruyemiş", 300, "Kg"),
        ("Kuru Üzüm (İzmir)", "Kuruyemiş", 250, "Kg"),
        ("Ceviz", "Kuruyemiş", 225, "Kg"),
        ("Karpuz Çekirdeği", "Kuruyemiş", 260, "Kg"),
        ("Soslu Mısır", "Kuruyemiş", 140, "Kg"),
        ("Soslu Yerfıstığı", "Kuruyemiş", 140, "Kg"),
        ("Karışık Atom Çerez", "Kuruyemiş", 220, "Kg"),
        ("Çıtır Leblebi", "Kuruyemiş", 175, "Kg"),
        ("Kaju", "Kuruyemiş", 600, "Kg"),

        ("Kelebek Sucuk", "Lokum", 225, "Adet"),
        ("Çifte Kavrulmuş Lokum", "Lokum", 300, "Kg"),
        ("Fındıklı Lokum", "Lokum", 300, "Kg"),
        ("Kuş Lokumu", "Lokum", 175, "Kg"),
        ("Sadrazam Lokum", "Lokum", 200, "Kg"),
        ("Sade Lokum", "Lokum", 200, "Kg"),

        ("Nar Ekşisi ", "Ekşi", 150, "700 Gr"),

        ("Enginar Sirkesi ", "Sirke", 90, "500 ml"),
        ("Ananas Sirkesi ", "Sirke", 90, "500 ml"),
        ("Alıç Sirkesi ", "Sirke", 90, "500 ml"),
        ("Elma Sirkesi ", "Sirke", 90, "500 ml"),
        ("Üzüm Sirkesi ", "Sirke", 90, "500 ml"),
        ("Limon Sarımsak Zencefil Karışımlı Sirke ", "Sirke", 90, "500 ml"),
        ("Nar Sirkesi ", "Sirke", 90, "500 ml"),
        ("Kozalak Şurubu ", "Sirke", 85, "500 ml"),
    ]

    for name, category, price, unit in products:
        p = Product(name=name, category=category, price=price, unit=unit, image="/static/images/placeholder.png")
        db.session.add(p)

    db.session.commit()
    print("✅ Ürünler başarıyla veritabanına eklendi!")

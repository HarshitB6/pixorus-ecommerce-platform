from flask import Flask, render_template, request, redirect, session, jsonify, flash
from werkzeug.security import generate_password_hash, check_password_hash
import mysql.connector, os

app = Flask(__name__)
app.secret_key = "pixorus_secret_2025"

DEFAULT_PRODUCTS = [
    (
        "Laptop Pro",
        54999,
        "/static/images/laptop.webp",
        "High-performance laptop for professionals",
        1,
    ),
    (
        "Running Shoes",
        2499,
        "/static/images/running-shoes.jpg",
        "Lightweight running shoes",
        2,
    ),
    (
        "Noise-Cancelling Headphones",
        3499,
        "/static/images/headphones.webp",
        "Studio-quality sound",
        1,
    ),
    (
        "Classic T-Shirt",
        899,
        "/static/images/t-shirt.jpg",
        "100% cotton comfort tee",
        3,
    ),
    (
        "Smart Watch",
        8999,
        "/static/images/smart-watch.jpg",
        "Fitness tracking smartwatch",
        4,
    ),
    (
        "Gaming Mouse",
        1799,
        "/static/images/mouse.webp",
        "Precision RGB gaming mouse",
        5,
    ),
    (
        "Leather Wallet",
        699,
        "/static/images/wallet.webp",
        "Slim genuine leather wallet",
        4,
    ),
    (
        "Wireless Earbuds",
        2199,
        "/static/images/earbuds.webp",
        "True wireless earbuds 30hr battery",
        1,
    ),
]

# =========================
# MYSQL CONFIG
# =========================
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "root123",        
    "database": "pixorus"
}

def get_db():
    conn = mysql.connector.connect(**DB_CONFIG)
    return conn

def dict_cursor(conn):
    return conn.cursor(dictionary=True)

def db_val(conn, query, params=None):
    """Execute a query and return the first value of the first row."""
    c = conn.cursor()
    c.execute(query, params or ())
    row = c.fetchone()
    return row[0] if row else None

def db_execute(conn, query, params=None, fetch=None):
    c = conn.cursor(dictionary=True)
    c.execute(query, params or ())

    # Detect SELECT automatically
    if query.strip().lower().startswith("select"):
        if fetch == "one":
            result = c.fetchone()
        else:
            result = c.fetchall()
        c.close()
        return result

    # For INSERT / UPDATE / DELETE
    conn.commit()
    c.close()
    return None


def repair_default_product_images(cursor):
    random_image_patterns = (
        "https://picsum.photos/%",
        "http://picsum.photos/%",
        "https://source.unsplash.com/%",
        "http://source.unsplash.com/%",
    )

    for name, _price, image, _desc, _cat in DEFAULT_PRODUCTS:
        placeholders = " OR ".join(["image LIKE %s"] * len(random_image_patterns))
        cursor.execute(
            f"""
            UPDATE products
            SET image=%s
            WHERE name=%s
              AND (image IS NULL OR image='' OR {placeholders})
            """,
            (image, name, *random_image_patterns),
        )


def init_db():
    # First connect without selecting a DB to create it if needed
    base = mysql.connector.connect(
        host=DB_CONFIG["host"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"]
    )
    bc = base.cursor()
    bc.execute("CREATE DATABASE IF NOT EXISTS pixorus")
    base.commit()
    base.close()

    conn = get_db()
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id INT PRIMARY KEY AUTO_INCREMENT,
        name VARCHAR(100) NOT NULL,
        email VARCHAR(100) UNIQUE NOT NULL,
        password VARCHAR(255) NOT NULL,
        is_admin TINYINT DEFAULT 0
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS categories (
        id INT PRIMARY KEY AUTO_INCREMENT,
        name VARCHAR(100) NOT NULL
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS products (
        id INT PRIMARY KEY AUTO_INCREMENT,
        name VARCHAR(150) NOT NULL,
        price DECIMAL(10,2) NOT NULL,
        image TEXT,
        description TEXT,
        category_id INT,
        stock INT DEFAULT 100,
        FOREIGN KEY(category_id) REFERENCES categories(id)
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS cart (
        id INT PRIMARY KEY AUTO_INCREMENT,
        user_id INT NOT NULL,
        product_id INT NOT NULL,
        quantity INT DEFAULT 1,
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(product_id) REFERENCES products(id)
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS orders (
        id INT PRIMARY KEY AUTO_INCREMENT,
        user_id INT NOT NULL,
        total DECIMAL(10,2) NOT NULL,
        status VARCHAR(50) DEFAULT 'Processing',
        address TEXT,
        phone VARCHAR(20),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS order_items (
        id INT PRIMARY KEY AUTO_INCREMENT,
        order_id INT NOT NULL,
        product_id INT NOT NULL,
        quantity INT NOT NULL,
        price DECIMAL(10,2) NOT NULL,
        FOREIGN KEY(order_id) REFERENCES orders(id),
        FOREIGN KEY(product_id) REFERENCES products(id)
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS reviews (
        id INT PRIMARY KEY AUTO_INCREMENT,
        user_id INT NOT NULL,
        product_id INT NOT NULL,
        rating INT NOT NULL,
        comment TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(product_id) REFERENCES products(id)
    )""")

    # Seed categories
    c.execute("SELECT COUNT(*) FROM categories")
    if c.fetchone()[0] == 0:
        cats = ["Electronics", "Footwear", "Clothing", "Accessories", "Gaming"]
        for cat in cats:
            c.execute("INSERT INTO categories (name) VALUES (%s)", (cat,))

    # Seed products
    c.execute("SELECT COUNT(*) FROM products")
    if c.fetchone()[0] == 0:
        for name, price, img, desc, cat in DEFAULT_PRODUCTS:
            c.execute("INSERT INTO products (name, price, image, description, category_id) VALUES (%s,%s,%s,%s,%s)",
                      (name, price, img, desc, cat))

    repair_default_product_images(c)

    # Seed admin user
    c.execute("SELECT COUNT(*) FROM users WHERE is_admin=1")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO users (name, email, password, is_admin) VALUES (%s,%s,%s,%s)",
                  ("Admin", "admin@pixorus.com", generate_password_hash("admin123"), 1))

    conn.commit()
    conn.close()

# =========================
# HELPERS
# =========================
def current_user():
    uid = session.get('user_id')
    if not uid:
        return None
    conn = get_db()
    user = db_execute(conn, "SELECT * FROM users WHERE id=%s", (uid,), fetch="one")
    conn.close()
    return user

def cart_count():
    uid = session.get('user_id')
    if not uid:
        return 0
    conn = get_db()
    row = db_val(conn, "SELECT SUM(quantity) FROM cart WHERE user_id=%s", (uid,))
    conn.close()
    return row or 0
@app.template_filter('format_date')
def format_date(value):
    if value is None:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    return str(value)[:10]

# =========================
# HOME
# =========================
@app.route('/')
def home():
    conn = get_db()
    q = request.args.get('q', '')
    cat_id = request.args.get('cat', '')

    query = "SELECT p.*, c.name as category FROM products p LEFT JOIN categories c ON p.category_id=c.id WHERE 1=1"
    params = []
    if q:
        query += " AND p.name LIKE %s"
        params.append(f'%{q}%')
    if cat_id:
        query += " AND p.category_id=%s"
        params.append(cat_id)

    products = db_execute(conn, query, params, fetch="all")
    categories = db_execute(conn, "SELECT * FROM categories", fetch="all")
    category_lookup = {cat['name']: cat['id'] for cat in categories}

    # Recommendation: most added to cart
    recommended = db_execute(conn, """
        SELECT p.*, COUNT(c.id) as freq
        FROM products p
        LEFT JOIN cart c ON p.id = c.product_id
        GROUP BY p.id
        ORDER BY freq DESC
        LIMIT 4
    """, fetch="all")

    conn.close()
    return render_template('index.html',
                           products=products,
                           categories=categories,
                           category_lookup=category_lookup,
                           recommended=recommended,
                           user=current_user(),
                           cart_count=cart_count(),
                           q=q, cat_id=cat_id)

# =========================
# PRODUCT DETAIL
# =========================
@app.route('/product/<int:id>')
def product_detail(id):
    conn = get_db()
    product = db_execute(conn, "SELECT p.*, c.name as category FROM products p LEFT JOIN categories c ON p.category_id=c.id WHERE p.id=%s", (id,), fetch="one")
    if not product:
        conn.close()
        return redirect('/')
    reviews = db_execute(conn, """
        SELECT r.*, u.name as username FROM reviews r
        JOIN users u ON r.user_id=u.id
        WHERE r.product_id=%s
        ORDER BY r.created_at DESC
    """, (id,), fetch="all")
    avg_row = db_execute(conn, "SELECT AVG(rating) AS avg_rating FROM reviews WHERE product_id=%s", (id,), fetch="one")
    avg_rating = avg_row['avg_rating'] if avg_row else None
    # Similar products: same category
    similar = db_execute(conn, "SELECT * FROM products WHERE category_id=%s AND id!=%s LIMIT 4", (product['category_id'], id), fetch="all")
    conn.close()
    return render_template('product.html', product=product, reviews=reviews,
                           avg_rating=round(avg_rating, 1) if avg_rating else None,
                           similar=similar,
                           user=current_user(), cart_count=cart_count())

# =========================
# ADD REVIEW
# =========================
@app.route('/add_review/<int:product_id>', methods=['POST'])
def add_review(product_id):
    uid = session.get('user_id')
    if not uid:
        return redirect('/login')
    rating = int(request.form['rating'])
    comment = request.form.get('comment', '')
    conn = get_db()
    db_execute(conn, "INSERT INTO reviews (user_id, product_id, rating, comment) VALUES (%s,%s,%s,%s)", (uid, product_id, rating, comment))
    conn.commit()
    conn.close()
    return redirect(f'/product/{product_id}')

# =========================
# REGISTER
# =========================
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        conn = get_db()
        try:
            db_execute(conn, "INSERT INTO users (name, email, password) VALUES (%s,%s,%s)", (name, email, generate_password_hash(password)))
            conn.commit()
            conn.close()
            return redirect('/login')
        except mysql.connector.IntegrityError:
            conn.close()
            return render_template('register.html', error="Email already registered!", user=None, cart_count=0)
    return render_template('register.html', user=None, cart_count=0)

# =========================
# LOGIN
# =========================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        conn = get_db()
        user = db_execute(conn, "SELECT * FROM users WHERE email=%s", (email,), fetch="one")
        conn.close()
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            return redirect('/')
        return render_template('login.html', error="Invalid email or password", user=None, cart_count=0)
    return render_template('login.html', user=None, cart_count=0)

# =========================
# LOGOUT
# =========================
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

# =========================
# CART
# =========================
@app.route('/cart')
def cart_page():
    uid = session.get('user_id')
    if not uid:
        return redirect('/login')
    conn = get_db()
    items = db_execute(conn, """
        SELECT p.id, p.name, p.price, p.image, p.stock, c.quantity, (p.price * c.quantity) as subtotal
        FROM cart c JOIN products p ON c.product_id=p.id
        WHERE c.user_id=%s
    """, (uid,), fetch="all")
    total = sum(i['subtotal'] for i in items)
    conn.close()
    return render_template('cart.html', items=items, total=total, user=current_user(), cart_count=cart_count())

@app.route('/add_to_cart/<int:id>')
def add_to_cart(id):
    uid = session.get('user_id')
    if not uid:
        return redirect('/login')
    conn = get_db()
    product = db_execute(conn, "SELECT name, stock FROM products WHERE id=%s", (id,), fetch="one")
    if not product:
        conn.close()
        return redirect('/')
    if product['stock'] <= 0:
        conn.close()
        flash(f"{product['name']} is out of stock.")
        return redirect(request.referrer or '/')

    existing = db_execute(conn, "SELECT * FROM cart WHERE user_id=%s AND product_id=%s", (uid, id), fetch="one")
    if existing:
        if existing['quantity'] >= product['stock']:
            conn.close()
            flash(f"Only {product['stock']} units of {product['name']} are available.")
            return redirect('/cart')
        db_execute(conn, "UPDATE cart SET quantity=quantity+1 WHERE user_id=%s AND product_id=%s", (uid, id))
    else:
        db_execute(conn, "INSERT INTO cart (user_id, product_id, quantity) VALUES (%s,%s,1)", (uid, id))
    conn.commit()
    conn.close()
    return redirect('/cart')

@app.route('/remove_from_cart/<int:id>')
def remove_from_cart(id):
    uid = session.get('user_id')
    if not uid:
        return redirect('/login')
    conn = get_db()
    db_execute(conn, "DELETE FROM cart WHERE user_id=%s AND product_id=%s", (uid, id))
    conn.commit()
    conn.close()
    return redirect('/cart')

@app.route('/update_cart/<int:id>', methods=['POST'])
def update_cart(id):
    uid = session.get('user_id')
    if not uid:
        return redirect('/login')
    qty = int(request.form['quantity'])
    conn = get_db()
    if qty <= 0:
        db_execute(conn, "DELETE FROM cart WHERE user_id=%s AND product_id=%s", (uid, id))
    else:
        product = db_execute(conn, "SELECT name, stock FROM products WHERE id=%s", (id,), fetch="one")
        if not product:
            conn.close()
            return redirect('/cart')
        if qty > product['stock']:
            qty = product['stock']
            flash(f"Only {product['stock']} units of {product['name']} are available. Cart quantity was adjusted.")
        db_execute(conn, "UPDATE cart SET quantity=%s WHERE user_id=%s AND product_id=%s", (qty, uid, id))
    conn.commit()
    conn.close()
    return redirect('/cart')

# =========================
# CHECKOUT
# =========================
@app.route('/checkout', methods=['GET', 'POST'])
@app.route('/api/checkout', methods=['POST'])
def checkout():
    uid = session.get('user_id')
    if not uid:
        return redirect('/login')
    conn = get_db()
    if request.method == 'POST':
        address = request.form['address']
        phone = request.form['phone']
        items = db_execute(conn, """
            SELECT p.name, p.price, p.stock, c.quantity, c.product_id
            FROM cart c JOIN products p ON c.product_id=p.id WHERE c.user_id=%s
        """, (uid,), fetch="all")
        if not items:
            conn.close()
            return redirect('/cart')

        for item in items:
            if item['quantity'] > item['stock']:
                conn.close()
                flash(f"Only {item['stock']} units of {item['name']} are available.")
                return redirect('/cart')

        total = sum(i['price'] * i['quantity'] for i in items)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO orders (user_id, total, address, phone) VALUES (%s,%s,%s,%s)",
            (uid, total, address, phone)
        )
        conn.commit()
        order_id = cur.lastrowid
        cur.close()

        for item in items:
            db_execute(conn, "INSERT INTO order_items (order_id, product_id, quantity, price) VALUES (%s,%s,%s,%s)", (order_id, item['product_id'], item['quantity'], item['price']))
            db_execute(conn, "UPDATE products SET stock=stock-%s WHERE id=%s", (item['quantity'], item['product_id']))
        db_execute(conn, "DELETE FROM cart WHERE user_id=%s", (uid,))
        conn.commit()
        conn.close()
        return redirect('/orders')

    items = db_execute(conn, """
        SELECT p.name, p.price, p.stock, c.quantity, (p.price*c.quantity) as subtotal
        FROM cart c JOIN products p ON c.product_id=p.id WHERE c.user_id=%s
    """, (uid,), fetch="all")
    total = sum(i['subtotal'] for i in items)
    conn.close()
    return render_template('checkout.html', items=items, total=total, user=current_user(), cart_count=cart_count())

# =========================
# ORDERS
# =========================
# =========================
# ORDERS
# =========================
@app.route('/orders')
def orders_page():
    uid = session.get('user_id')
    if not uid:
        return redirect('/login')
    conn = get_db()
    orders = db_execute(conn, "SELECT * FROM orders WHERE user_id=%s ORDER BY created_at DESC", (uid,), fetch="all")
    order_items = {}
    for o in orders:
        items = db_execute(conn, """
            SELECT oi.*, p.name, p.image FROM order_items oi
            JOIN products p ON oi.product_id=p.id WHERE oi.order_id=%s
        """, (o['id'],), fetch="all")
        order_items[o['id']] = items
    conn.close()
    return render_template('orders.html', orders=orders, order_items=order_items, user=current_user(), cart_count=cart_count())

# =========================
# ADMIN
# =========================
@app.route('/admin')
def admin():
    uid = session.get('user_id')
    user = current_user()
    if not user or not user['is_admin']:
        return redirect('/')
    conn = get_db()
    users = db_execute(conn, "SELECT * FROM users", fetch="all")
    products = db_execute(conn, "SELECT p.*, c.name as category FROM products p LEFT JOIN categories c ON p.category_id=c.id", fetch="all")
    orders = db_execute(conn, "SELECT o.*, u.name as username FROM orders o JOIN users u ON o.user_id=u.id ORDER BY o.created_at DESC", fetch="all")
    categories = db_execute(conn, "SELECT * FROM categories", fetch="all")
    total_revenue_row = db_execute(conn, "SELECT SUM(total) AS total_revenue FROM orders WHERE status='Delivered'", fetch="one")
    total_orders_row = db_execute(conn, "SELECT COUNT(*) AS total_orders FROM orders", fetch="one")
    total_revenue = total_revenue_row['total_revenue'] or 0
    total_orders = total_orders_row['total_orders']
    conn.close()
    return render_template('admin.html', users=users, products=products, orders=orders,
                           categories=categories, total_revenue=total_revenue,
                           total_orders=total_orders, user=user, cart_count=0)

@app.route('/add_product', methods=['POST'])
def add_product():
    user = current_user()
    if not user or not user['is_admin']:
        return redirect('/')
    conn = get_db()
    stock = int(request.form.get('stock') or 100)
    db_execute(conn, "INSERT INTO products (name, price, image, description, category_id, stock) VALUES (%s,%s,%s,%s,%s,%s)",
                 (request.form['name'], float(request.form['price']),
                  request.form['image'], request.form['description'],
                  int(request.form['category_id']), stock))
    conn.commit()
    conn.close()
    return redirect('/admin')

@app.route('/update_product/<int:id>', methods=['POST'])
def update_product(id):
    user = current_user()
    if not user or not user['is_admin']:
        return redirect('/')
    conn = get_db()
    db_execute(conn, """
        UPDATE products
        SET name=%s, price=%s, image=%s, description=%s, category_id=%s, stock=%s
        WHERE id=%s
    """, (
        request.form['name'],
        float(request.form['price']),
        request.form['image'],
        request.form['description'],
        int(request.form['category_id']),
        int(request.form.get('stock') or 0),
        id,
    ))
    conn.commit()
    conn.close()
    return redirect('/admin')

@app.route('/delete_product/<int:id>')
def delete_product(id):
    user = current_user()
    if not user or not user['is_admin']:
        return redirect('/')
    conn = get_db()
    db_execute(conn, "DELETE FROM products WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    return redirect('/admin')

@app.route('/update_order_status/<int:id>', methods=['POST'])
def update_order_status(id):
    user = current_user()
    if not user or not user['is_admin']:
        return redirect('/')
    status = request.form['status']
    conn = get_db()
    db_execute(conn, "UPDATE orders SET status=%s WHERE id=%s", (status, id))
    conn.commit()
    conn.close()
    return redirect('/admin')

# =========================
# RUN
# =========================
if __name__ == "__main__":
    init_db()
    app.run(debug=True)

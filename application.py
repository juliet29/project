from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions
from werkzeug.security import check_password_hash, generate_password_hash

#import pdb

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure responses aren't cached
if app.config["DEBUG"]:
    @app.after_request
    def after_request(response):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Expires"] = 0
        response.headers["Pragma"] = "no-cache"
        return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # get names of different types of stocks owned
    stocks = db.execute(
        "SELECT DISTINCT stock FROM transactions WHERE userId = :user", user=session["user_id"])
    stockList = [stockDict['stock'] for stockDict in stocks]

    # get total of shares owned per stock
    sharesList = []
    stockListNew = []
    for i in stockList:
        sharesDict = db.execute(
            "SELECT SUM (shares) FROM transactions WHERE userId = :user AND stock = :stock1", user=session["user_id"], stock1=i)
        if not sharesDict:
            return apology("Server is currently down")
        if sharesDict[0]['SUM (shares)'] != 0:
            total_shares = sharesDict[0]['SUM (shares)']
            # create a new list of stocks for which the user still owns shares
            sharesList.append(total_shares)
            stockListNew.append(i)

    # get current price of each valid stock
    current_price = [float(lookup(symbol)["price"]) for symbol in stockListNew]

    # get total value of holdings of a specific stock
    holdingList = [sharesList[i] * current_price[i] for i in range(len(sharesList))]

    # get current amount of cash the user has
    cash_list = db.execute("SELECT cash FROM users WHERE id = :user", user=session["user_id"])
    cash = cash_list[0]["cash"]

    # calculate the users total wealth
    total_holdings = sum(holdingList)
    total = cash + total_holdings

    # disregard difference between purchase or sale when displaying index
    sharesList = [abs(share) for share in sharesList]
    holdingList = [abs(holding) for holding in holdingList]

    # show user the table
    return render_template("index.html", total=total, cash=cash, stock=stockListNew, shares=sharesList, price=current_price, holding=holdingList)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "GET":
        return render_template("buy.html")
    else:
        # find the stock and its current price
        symbol = request.form.get("symbol")
        stock = lookup(symbol)
        if not stock:
            return apology("Stock does not exist", 400)
        stock_price = stock["price"]
        stock_symbol = stock["symbol"]

        # find the number of shares the user wants to buy
        shares = request.form.get("shares")
        if shares.isnumeric():
            shares = float(shares)
            if shares <= 0:
                return apology("Invalid input")
            elif shares % 1 != 0:
                return apology("Invalid input")
        else:
            return apology("Invalid input")

        # find out how much cash the user has
        cash_list = db.execute("SELECT cash FROM users WHERE id = :user", user=session["user_id"])
        cash = cash_list[0]["cash"]

        # ensure the user can afford the purchase
        holding = shares * stock_price
        if holding > cash:
            return apology("Not enough cash")
        else:
            # record purchase in transactions list
            db.execute("INSERT INTO transactions (userId, stock, price, shares, holding) VALUES (:user, :stock_name, :stock_price, :shares, :holding)",
                       user=session["user_id"], stock_name=stock["name"], stock_price=stock["price"], shares=shares, holding=-holding)

            # remove cash from the user
            db.execute("UPDATE users SET cash = :newCash WHERE id = :user",
                       newCash=cash - holding, user=session["user_id"])

        # show user that the purchase has occured in the index page
        return redirect("/")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    if not db.execute("SELECT shares FROM transactions WHERE userId = :user", user=session["user_id"]):
        return(apology("Need to make a purchase to have history"))

    # get list of timestamps
    purchaseTimes = db.execute(
        "SELECT purchaseTime FROM transactions WHERE userId = :user", user=session["user_id"])
    purchaseTimeList = [purchaseTimeDict['purchaseTime'] for purchaseTimeDict in purchaseTimes]

    # get list of stocks for each transaction
    stocks = db.execute("SELECT stock FROM transactions WHERE userId = :user",
                        user=session["user_id"])
    stockList = [stockDict['stock'] for stockDict in stocks]

    # get list of shares sold at each transaction
    shares = db.execute("SELECT shares FROM transactions WHERE userId = :user",
                        user=session["user_id"])
    sharesList = [sharesDict['shares'] for sharesDict in shares]

    # get list of prices of each stock at time of transaction
    prices = db.execute("SELECT price FROM transactions WHERE userId = :user",
                        user=session["user_id"])
    priceList = [float(priceDict['price']) for priceDict in prices]

    # show user their purchase history
    return render_template("history.html", purchaseTime=purchaseTimeList, stock=stockList, shares=sharesList, price=priceList)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 400)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "GET":
        return render_template("quote.html")
    else:
        # retrieve stock quote
        quote = lookup(request.form.get("symbol"))
        # apologize if user does not input a valid stock
        if not quote:
            return apology("Stock does not exist", 400)
        return render_template("quoted.html", name=quote["name"], price=quote["price"], symbol=quote["symbol"])


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":

        username = request.form.get("username")

        # check that username is a valid entry
        if not request.form.get("username"):
            return apology("Enter username!", 400)

        # check that username is not already in the database, personal touch
        userId = db.execute("SELECT username FROM users WHERE username = :user",
                            user=request.form.get("username"))
        if userId:
            if username == userId[0]["username"] or username.isalpha() or len(username) < 5:
                return apology("Pick another username", code=400)

        # check that password has been entered
        if not request.form.get("password"):
            return apology("Enter password!", code=400)

        # check that passwords match
        if request.form.get("password") != request.form.get("confirmation"):
            return apology("Passwords don't match!", code=400)
        else:
            phash = generate_password_hash(request.form.get("password"))

        # insert user to database
        result = db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)",
                            username=request.form.get("username"), hash=phash)
        if not result:
            return apology("Registration failed", 200)

        else:
            # log in
            session["user_id"] = result

        # redirect user to home page
        return redirect("/")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "GET":
        stocks = db.execute(
            "SELECT DISTINCT stock FROM transactions WHERE userId = :user", user=session["user_id"])
        stockList = [stockDict['stock'] for stockDict in stocks]
        return render_template("sell.html", stock=stockList)
    else:
        # find the stock and its current price
        stock = lookup(request.form.get("symbol"))
        if not stock:
            return apology("Stock does not exist", 400)
        stock_price = stock["price"]
        stock_name = stock["symbol"]

        # find the number of shares the user wants to sell
        shares = request.form.get("shares")
        if shares.isnumeric():
            shares = float(shares)
            if shares <= 0:
                return apology("Invalid input")
            elif shares % 1 != 0:
                return apology("Invalid input")
        else:
            return apology("Invalid input")

        # check that the user has enough stocks to sell
        shares_owned_list = db.execute("SELECT SUM (shares) FROM transactions WHERE userId = :user AND stock = :stock_name",
                                       user=session["user_id"], stock_name=stock["name"])
        if not shares_owned_list:
            return apology("Server Error")
        shares_owned = shares_owned_list[0]["SUM (shares)"]
        if shares > abs(shares_owned):
            return apology("You don't have enough stocks to sell")

        # find out how much cash the user has
        cash_list = db.execute("SELECT cash FROM users WHERE id = :user", user=session["user_id"])
        cash = cash_list[0]["cash"]

        # find total value of sale
        holding = (shares * stock_price)

        # record sale in transactions list
        db.execute("INSERT INTO transactions (userId, stock, price, shares, holding) VALUES (:user, :stock_name, :stock_price, :shares, :holding)",
                   user=session["user_id"], stock_name=stock["name"], stock_price=stock["price"], shares=-shares, holding=holding)

        # remove cash from the user
        db.execute("UPDATE users SET cash = :newCash WHERE id = :user",
                   newCash=cash + holding, user=session["user_id"])

        # show user that the purchase has occured in the index page
        return redirect("/")


def errorhandler(e):
    """Handle error"""
    return apology(e.name, e.code)


# listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
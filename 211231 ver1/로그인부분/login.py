from flask import Flask, render_template, jsonify, request, session, redirect, url_for
import certifi
app = Flask(__name__)

from pymongo import MongoClient
ca = certifi.where()
# client = MongoClient('mongodb+srv://test:sparta@cluster0.p2cn0.mongodb.net/Cluster0?retryWrites=true&w=majority')
client = MongoClient('mongodb+srv://test:sparta@cluster0.rtjyu.mongodb.net/Cluster0?retryWrites=true&w=majority', tlsCAFile=ca)
db = client.dbsparta

# JWT 토큰을 만들 때 필요한 비밀문자열입니다. 아무거나 입력해도 괜찮습니다.
# 이 문자열은 서버만 알고있기 때문에, 내 서버에서만 토큰을 인코딩(=만들기)/디코딩(=풀기) 할 수 있습니다.
SECRET_KEY = 'SPARTA'

# JWT 패키지를 사용합니다. (설치해야할 패키지 이름: PyJWT)
import jwt

# 토큰에 만료시간을 줘야하기 때문에, datetime 모듈도 사용합니다.
import datetime

# 회원가입 시엔, 비밀번호를 암호화하여 DB에 저장해두는 게 좋습니다.
# 그렇지 않으면, 개발자(=나)가 회원들의 비밀번호를 볼 수 있으니까요.^^;
import hashlib


#################################
##  HTML을 주는 부분             ##
#################################
@app.route('/')
def home():
    # 현재 이용자의 컴퓨터에 저장된 cookie 에서 mytoken 을 가져옵니다.
    token_receive = request.cookies.get('mytoken')
    try:
        # 암호화되어있는 token의 값을 우리가 사용할 수 있도록 디코딩(암호화 풀기)해줍니다!
        payload = jwt.decode(token_receive, SECRET_KEY, algorithms=['HS256'])
        user_info = db.user.find_one({"id": payload['id']})
        return render_template('home.html', id=user_info["id"])
    # 만약 해당 token의 로그인 시간이 만료되었다면, 아래와 같은 코드를 실행합니다.
    except jwt.ExpiredSignatureError:
        return redirect(url_for("login", msg="로그인 시간이 만료되었습니다."))
    except jwt.exceptions.DecodeError:
        # 만약 해당 token이 올바르게 디코딩되지 않는다면, 아래와 같은 코드를 실행합니다.
        return redirect(url_for("login", msg="로그인 정보가 존재하지 않습니다."))


@app.route('/login')
def login():
    msg = request.args.get("msg")
    return render_template('login.html', msg=msg)


@app.route('/register')
def register():
    return render_template('register.html')


#################################
##  로그인을 위한 API            ##
#################################

# [회원가입 API]
# id, pw, nickname을 받아서, mongoDB에 저장합니다.
# 저장하기 전에, pw를 sha256 방법(=단방향 암호화. 풀어볼 수 없음)으로 암호화해서 저장합니다.
@app.route('/api/register', methods=['POST'])
def api_register():
    id_receive = request.form['id_give']
    pw_receive = request.form['pw_give']
    name_receive = request.form['name_give']
    email_receive = request.form['email_give']

    pw_hash = hashlib.sha256(pw_receive.encode('utf-8')).hexdigest()

    db.user.insert_one({'id': id_receive, 'pw': pw_hash, 'name': name_receive, 'email': email_receive})

    return jsonify({'result': 'success'})

#############로그인 중복확인 서버##############################
@app.route('/check_dup', methods=['POST'])
def check_dup():
    userid_receive = request.form['userid_give']
    exists = bool(db.user.find_one({"id": userid_receive}))
    return jsonify({'result': 'success', 'exists': exists})


############################################################



# [로그인 API]
# id, pw를 받아서 맞춰보고, 토큰을 만들어 발급합니다.
@app.route('/api/login', methods=['POST'])
def api_login():
    id_receive = request.form['id_give']
    pw_receive = request.form['pw_give']

    # 회원가입 때와 같은 방법으로 pw를 암호화합니다.
    pw_hash = hashlib.sha256(pw_receive.encode('utf-8')).hexdigest()

    # id, 암호화된pw을 가지고 해당 유저를 찾습니다.
    result = db.user.find_one({'id': id_receive, 'pw': pw_hash})

    # 찾으면 JWT 토큰을 만들어 발급합니다.
    if result is not None:
        # JWT 토큰에는, payload와 시크릿키가 필요합니다.
        # 시크릿키가 있어야 토큰을 디코딩(=암호화 풀기)해서 payload 값을 볼 수 있습니다.
        # 아래에선 id와 exp를 담았습니다. 즉, JWT 토큰을 풀면 유저ID 값을 알 수 있습니다.
        # exp에는 만료시간을 넣어줍니다. 만료시간이 지나면, 시크릿키로 토큰을 풀 때 만료되었다고 에러가 납니다.
        payload = {
            'id': id_receive,
            'exp': datetime.datetime.utcnow() + datetime.timedelta(minutes=500)
        }
        token = jwt.encode(payload, SECRET_KEY, algorithm='HS256')

        # token을 줍니다.
        return jsonify({'result': 'success', 'token': token})
    # 찾지 못하면
    else:
        return jsonify({'result': 'fail', 'msg': '아이디/비밀번호가 일치하지 않습니다.'})


# [유저 정보 확인 API]
# 로그인된 유저만 call 할 수 있는 API입니다.
# 유효한 토큰을 줘야 올바른 결과를 얻어갈 수 있습니다.
# (그렇지 않으면 남의 장바구니라든가, 정보를 누구나 볼 수 있겠죠?)
@app.route('/api/user', methods=['GET'])
def api_valid():
    token_receive = request.cookies.get('mytoken')

    # try / catch 문?
    # try 아래를 실행했다가, 에러가 있으면 except 구분으로 가란 얘기입니다.

    try:
        # token을 시크릿키로 디코딩합니다.
        # 보실 수 있도록 payload를 print 해두었습니다. 우리가 로그인 시 넣은 그 payload와 같은 것이 나옵니다.
        payload = jwt.decode(token_receive, SECRET_KEY, algorithms=['HS256'])

        # print(payload)에는 회원정보때 입력했던 것들이 들어감

        # payload 안에 id가 들어있습니다. 이 id로 유저정보를 찾습니다.
        # 여기에선 그 예로 닉네임을 보내주겠습니다.
        userinfo = db.user.find_one({'id': payload['id']}, {'_id': 0})
        return jsonify({'result': 'success', 'id': userinfo['id']})
    except jwt.ExpiredSignatureError:
        # 위를 실행했는데 만료시간이 지났으면 에러가 납니다.
        return jsonify({'result': 'fail', 'msg': '로그인 시간이 만료되었습니다.'})
    except jwt.exceptions.DecodeError:
        return jsonify({'result': 'fail', 'msg': '로그인 정보가 존재하지 않습니다.'})


#####################정훈님 코드#######################
@app.route('/posting')
def posting():
    return render_template('posting.html')


# @app.route("/posting", methods=["GET"])
# def posting_list_get():
#     posting_num = list(db.posting.find({'num'}, {'_id': False}))
#     return jsonify({'posting_list': posting_num})


# @app.route('/user', methods=['POST'])
# def posting_list_post():
#     posting_list = list(db.posting.find({}, {'_id': False}))
#     count = posting_list[:-1] + 1
#
#     doc = {
#         'num': count
#     }
#     db.posting.insert_one(doc)


@app.route('/posting', methods=['POST'])
def posting_post():
    url_receive = request.form['url_give']
    mylocation_receive = request.form['mylocation_give']
    mytime_receive = request.form['mytime_give']
    mytext_receive = request.form['mytext_give']
    writerid_receive = request.form['writerid_give']

    # posting_list = list(db.posting.find({}, {'_id': False}))
    posting_number = list(db.posting.find({}, {'_id': False}))
    count = len(posting_number) + 1

    doc = {
        'num': count,
        'url': url_receive,
        'mylocation': mylocation_receive,
        'mytime': mytime_receive,
        'mytext': mytext_receive,
        'writerid': writerid_receive
    }
    db.posting.insert_one(doc)

    return jsonify({'msg': '게시글 작성 완료'})

################################################################
## 피더부분################

@app.route('/feed_home')
def feed_home():
    return render_template('feed_index.html')


@app.route("/home", methods=["GET"])
def show_user():
    user_post = list(db.posting.find({}, {'_id': False}))
    # comment_post = list(db.comments.find({}, {'_id': False}))

    return jsonify({'post':user_post})

# @app.route("/homeid", methods=["GET"])
# def find_id():
#     get_id = list(db.user.find({}, {'_id': False}))
#
#     return jsonify({'info':get_id})


@app.route("/home", methods=["POST"])
def feed_post():
    comment_receive = request.form['comment_give']
    writerid_receive = request.form['writerid_give']

    comments_list = list(db.comments.find({}, {'_id': False}))
    count = len(comments_list) + 1

    doc = {
        'num': count,
        'comments': comment_receive,
        'writerid' : writerid_receive
    }

    db.comments.insert_one(doc)
    return jsonify({'msg':'저장 완료!'})

@app.route("/homecom", methods=["GET"])
def show_id():
    comment = list(db.comments.find({}, {'_id': False}))

    return jsonify({'com':comment})



if __name__ == '__main__':
    app.run('0.0.0.0', port=5000, debug=True)

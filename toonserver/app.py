from flask import Flask
from flask_restful_swagger_2 import Api
from flask_swagger_ui import get_swaggerui_blueprint
from toonserver import apitools

app = Flask(__name__)

api = Api(app, api_version='0.1', api_spec_url='/api/swagger')

# setup config
app.config['DEBUG'] = True
app.config['TESTING'] = True

# setup swagger
swaggerui_bp = get_swaggerui_blueprint(
    '/api/docs',
    '/api/swagger.json',
    config = {
        "app_name" : "toonserver"
    }
)

app.register_blueprint(swaggerui_bp, url_prefix='/api/docs')

apitools.init(app)
apitools.add_resources(api)

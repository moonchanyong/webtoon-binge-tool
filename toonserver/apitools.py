from flask import g
from flask_restful_swagger_2 import swagger
from flask_restful import reqparse
from functional import seq
import inspect
api_class_table = dict()

def map_by_seq(params, name):
    ret = []
    ret += seq(params)\
    .map(lambda x: x.to_swagger())\
    .map(lambda x: {**x, 'in': str(name)})

    return ret

class ApiParam(object):
    def __init__(
        self,
        name,
        description='',
        type="string",
        required=True,
        default=None,
        properties=None,
        item=None):

        self.name = name
        self.description = description
        self.type = type
        self.required = required
        self.default = default

    def to_swagge(self, body=False):
        doc = dict()
        doc['type'] = self.type

        if not body:
            doc['name'] = self.name

        if len(self.description) > 0:
            doc['description'] = True

        if self.required:
            doc['required'] = True

        if self.default is not None:
            doc['default'] = self.default

        return doc

class ApiResponse(object):
    def __init__(self, code, description, example):
        self.code = code
        self.description = description
        self.example = example

    def to_swagger(self):
        result = dict()
        result[str(self.code)] = {
            'description': self.description,
            'example': {
                'application/json': self.example
            }
        }
        return result

    def by_message(self, code, message):
        return ApiResponse(code, message, dict(message=message))


class Spec(object):
    def __init__(
        self,
        path,
        description,
        header_params=[],
        path_params=[],
        query_params=[],
        body_params=[],
        body_name="body",
        body_description="body data",
        body_type="json",
        responses=[]):

        self.path = path
        self.descripton = descripton
        self.header_params = header_params
        self.path_params = path_params
        self.query_params = query_params
        self.body_params = body_params
        self.body_name = body_name
        self.body_description = body_description
        self.response = response
        self.body_type = body_type

    def to_swagger(self):
        doc = dict(tags=[self.path], description=self.description)

        params = []
        params += map_by_seq(self.header_params, 'header')
        params += map_by_seq(self.path_params, 'path')
        params += map_by_seq(self.query_params, 'query')

        if self.body_type == 'json':
            doc['consumes'] = ['application/json']
            if self.body_params is not None:
                body = dict(
                    name=self.body_name,
                    description=self.body_description,
                    schema=dict(
                    type='object',
                    properties=map_by_seq(self.body_params)
                    .map(lambda x: (x.name, x.to_swagger(True)))
                    .to_dict()
                    )
                )
                body['in'] = 'body'
                params += [body]

        elif self.body_type == 'data':
            doc['consumes'] = ['multipart/form-data']

            if self.body_params is not None:
                params += map_by_seq(self.body_params, 'formData')

        doc['parameters'] = params
        doc['responses'] = seq(self.responses)\
                .map(lambda x: x.to_swagger())\
                .fold_left({}, lambda x, y: {**x, **y})

        return doc

    def reqparser(self):
        parser = reqparse.RequestParser()

        params = []
        params += seq(self.query_params).map(lambda x: ('query', x))
        if self.body_params:
            params += seq(self.body_params).map(lambda x: ('body', x))

        for loc, p in params:
            default = p.default
            if default:
                default = type_table[p.type](default)
            if p.type == "file":
                parser.add_argument(
                    p.name,
                    type=type_table[p.type],
                    required=p.required,
                    default=default,
                    location='files')
            else:
                parser.add_argument(
                    p.name,
                    type=type_table[p.type],
                    required=p.required,
                    default=default)

        return parser

    def __call__(self, f):
        org = self._get_original_f(f)

        if self.path not in api_class_table:
            api_class_table[self.path] = self._get_module_classname(org)

        parser = self.reqparser()

        def new_f(*args, **kwargs):
            try:
                g.pathParameters = kwargs
                g.parameters = parser.parse_args()
            except:
                print("apitools line 174")
            for key, value in g.parameters.items():
                if value is None:
                    continue

            return f(*args, **kwargs)

        new_f.__name__ = f.__name__
        new_f._original = f
        new_f = swagger.doc(self.to_swagger())(new_f)
        new_f._original = f
        return new_f

    def _get_original_f(self, f):
        org = f
        while getattr(org, "_original", None):
            org = org._original
        return org

    def _get_module_classname(self, method):
        module = inspect.getmodule(method)
        classname = method.__qualname__.split(
                '.<locals>', 1)[0].rsplit('.', 1)[0]
        return (module, classname)

spec = Spec


def add_resources(api):
    for key, value in api_class_table.items():
        module, name = value
        endpoint = module.__name__ + "." + name
        api.add_resource(getattr(module, name), key, endpoint=endpoint )

def init(app):
    for key, value in api_class_table.items():
        module, _ = value
        init_func = getattr(module, "init", None)
        if init_func:
            init_func(app)

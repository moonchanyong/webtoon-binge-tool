from flask import g
from flask_restful_swagger_2 import swagger
from flask_restful import reqparse
from functional import seq
import json
import inspect
# import arrow
from typing import Dict, List
from werkzeug.exceptions import HTTPException
from werkzeug.datastructures import FileStorage

api_class_table = dict()

# define types of primitives in json
json_primitives = set([
    'string', 'boolean', 'integer', 'number', 'object', 'array', 'dictionary',
    'file'])

# define using types in app
type_table = dict(
    string=str,
    boolean=lambda x: x.lower() in ('true', 'yes'),
    integer=int,
    number=float,
    object=lambda x: json.loads(x) if not isinstance(x, dict) else x,
    array=lambda x: json.loads(x) if not isinstance(x, list) else x,
    dictionary=lambda x: json.loads(x) if not isinstance(x, dict) else x)


class RangeConstraint(object):
    def __init__(self, min=None, max=None):
        self.min = min
        self.max = max

    def check(self, value):
        result = True
        result = result and (self.min is None or self.min <= value)
        result = result and (self.max is None or value <= self.max)
        return result

    def to_swagger(self):
        result = dict()
        if self.min is not None:
            result['minimum'] = self.min
        if self.max is not None:
            result['maximum'] = self.max
        return result


class LengthConstraint(object):
    def __init__(self, min=None, max=None):
        self.min = min
        self.max = max

    def check(self, value):
        result = True
        result = result and (self.min is None or self.min <= len(value))
        result = result and (self.max is None or len(value) <= self.max)
        return result

    def to_swagger(self):
        result = dict()
        if self.min is not None:
            result['minLength'] = self.min
        if self.max is not None:
            result['maxLength'] = self.max
        return result

class EnumConstraint(object):
    def __init__(self, enums):
        self.enums = enums

    def check(self, value):
        return value in self.enums

    def to_swagger(self):
        return dict(enum=self.enums)

class _ListConstraint(object):
    def __init__(self, constraints):
        self.constraints = constraints

    def check(self, items):
        pairs = seq(items).cartesian(self.constraints)
        return all([cons.check(item) for item, cons in pairs])

class _ObjectConstraint(object):
    def __init__(self, constraints_table: Dict[str, List]):
        self.constraints_table = constraints_table

    def check(self, table):
        pairs = seq(table.items()).join(self.constraints_table.items())
        pairs = [value for key, value in pairs]
        checks = all([cons.check(item)\
                for item, cons_list in pairs for cons in cons_list])
        return checks

class _ObjectRequireConstraint(object):
    def __init__(self, required_fields):
        self.required_fields = required_fields

    def check(self, value):
        nofields = seq(self.required_fields).difference(value.keys())
        return len(list(nofields)) == 0


class ApiParam(object):
    def __init__(
            self,
            name,
            description='',
            type="string",
            required=False,
            default=None,
            constraints=[],
            properties=None,
            item=None):

        self.name = name
        self.description = description
        self.type = type
        self.required = required
        self.default = default
        self.constraints = constraints
        self.properties = properties
        self.item = item

        if properties is not None:
            assert self.type == 'object'

        if item is not None:
            assert self.type == 'array'

        if self.type == 'object' and self.properties is None:
            self.properties = []

        if self.type == 'array' and self.item is None:
            self.item = ApiParam("item", "item", type='object')

    def get_tree_constrains(self):
        result = []
        result += self.constraints
        if self.type == 'array':
            result.append(_ListConstraint(self.item.get_tree_constrains()))
        elif self.type == 'object':
            table = {}
            for p in self.properties:
                table[p.name] = p.get_tree_constrains()
            result.append(_ObjectConstraint(table))

            required_fields = [field.name \
                    for field in self.properties if field.required]
            result = [_ObjectRequireConstraint(required_fields)] + result
        return result

    def to_swagger(self, body=False):
        doc = dict()
        if self.type not in json_primitives:
            doc['type'] = 'string'
            doc['format'] = self.type
        else:
            doc['type'] = self.type


        if not body:
            doc['name'] = self.name

        if len(self.description) > 0:
            doc['description'] = self.description

        if self.required:
            doc['required'] = True

        if self.default is not None:
            doc['default'] = self.default

        for cons in self.constraints:
            doc.update(cons.to_swagger())

        if self.type == 'object':
            doc['properties'] = seq(self.properties)\
                    .map(lambda x: (x.name, x.to_swagger(body)))\
                    .dict()
        elif self.type == 'array':
            doc['items'] = self.item.to_swagger(body)


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
            'examples': {
                'application/json': self.example
            }
        }
        return result


    @classmethod
    def error(cls, code, message):
        return ApiResponse(code, message, dict(message=message))


class Spec(object):
    def __init__(
            self,
            path,
            description,
            header_params=[],
            path_params=[],
            query_params=[],
            body_params=None,
            body_name="body",
            body_description="body data",
            body_type="json",
            responses=[]):

        self.path = path
        self.description = description
        self.header_params = header_params
        self.path_params = path_params
        self.query_params = query_params
        self.body_params = body_params
        self.body_name= body_name
        self.body_description = body_description
        self.responses = responses
        self.body_type= body_type

    def to_swagger(self):
        doc = dict(tags=[self.path], description=self.description)

        params = []
        params += seq(self.header_params)\
                    .map(lambda x: x.to_swagger())\
                    .map(lambda x: {**x, 'in': 'header'})

        params += seq(self.path_params)\
                    .map(lambda x: x.to_swagger())\
                    .map(lambda x: {**x, 'in': 'path'})

        params += seq(self.query_params)\
                    .map(lambda x: x.to_swagger())\
                    .map(lambda x: {**x, 'in': 'query'})

        if self.body_type == 'json':
            doc['consumes'] = ['application/json']
            if self.body_params is not None:
                body = dict(
                    name=self.body_name,
                    description=self.body_description,
                    schema=dict(
                        type='object',
                        properties=seq(self.body_params)\
                                    .map(lambda x: (x.name, x.to_swagger(True)))\
                                    .to_dict()
                    )
                )
                body['in'] = 'body'
                params += [body]


        elif self.body_type == 'data':
            doc['consumes'] = ['multipart/form-data']

            if self.body_params is not None:
                params += seq(self.body_params)\
                        .map(lambda x: x.to_swagger())\
                        .map(lambda x: {**x, 'in': 'formData'})

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

                parser.add_argument(
                    p.name,
                    type=type_table[p.type],
                    required=p.required,
                    default=default)

        return parser

    def constraint_table(self):
        params = []
        params += self.query_params

        if self.body_params:
            params += self.body_params

        table = dict()
        for param in params:
            table[param.name] = param.get_tree_constrains()

        return table

    def __call__(self, f):
        org = self._get_original_f(f)

        if self.path not in api_class_table:
            api_class_table[self.path] = self._get_module_classname(org)

        parser = self.reqparser()
        constraints = self.constraint_table()

        def new_f(*args, **kwargs):
            try:
                g.pathParameters = kwargs
                g.path = self.path
                g.parameters = parser.parse_args()
            except HTTPException as ex:
                if getattr(ex, 'data', None):
                    print("ParameterError",
                            payload=dict(parameters=ex.data['message']))
                else:
                    print("{}".format(ex))

            for key, value in g.parameters.items():
                if value is None:
                    continue
                passed = seq(constraints[key])\
                        .map(lambda x: x.check(value)).all()
                if not passed:
                    print("ParameterError",
                            payload=dict(parameters={key: "constraints error"}))


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


def get_path_args():
    return g.pathParameters
def get_args():
    return g.parameters
def get_path():
    return g.path

class Swagger:
    class Params:
        Authorization = [ApiParam('Authorization', 'Auth Token', required=True)]
        Page = [
            ApiParam('offset', 'offset of list (default: 0)',
                default=0, type='integer'),
            ApiParam('limit', 'limit of list (default: 20, min:1, max: 100)',
                default=20,
                type='integer',
                constraints=[RangeConstraint(1, 100)])
        ]

    class Responses:
        InvalidRequest = [ApiResponse.error(400, "Invalid Request")]

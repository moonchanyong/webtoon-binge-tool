from toonserver.apitools import spec, get_args,\
    ApiParam, ApiResponse, get_path_args, get_path
from flask_restful import Resource
from flask import g

class Test(Resource):
    @spec('/ping', 'ping test',
        query_params=[
            ApiParam('fruit', "what fruit like?")
        ],
        responses=[
            ApiResponse(200, 'Success', dict(message='success'))
        ]
    )
    def get(self):
        arg = get_args()
        return dict(message=arg)

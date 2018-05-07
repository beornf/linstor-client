import linstor.argparse.argparse as argparse
from linstor.utils import rangecheck, filter_new_args, namecheck
from linstor.commands import Commands
from linstor.consts import RES_NAME, NODE_NAME
from linstor.drbdsetup_options import drbd_options
import linstor.sharedconsts as apiconsts


class DrbdOptions(Commands):
    _options = drbd_options
    unsetprefix = 'unset'

    _CategoyMap = {
        'new-peer': apiconsts.NAMESPC_DRBD_NET_OPTIONS,
        'disk-options': apiconsts.NAMESPC_DRBD_DISK_OPTIONS,
        'resource-options': apiconsts.NAMESPC_DRBD_RESOURCE_OPTIONS,
        'peer-device-options': apiconsts.NAMESPC_DRBD_PEER_DEVICE_OPTIONS
    }

    def __init__(self):
        super(DrbdOptions, self).__init__()

    @classmethod
    def drbd_options(cls):
        return cls._options

    @staticmethod
    def numeric_symbol(_min, _max, _symbols):
        def foo(x):
            try:
                i = int(x)
                if i not in range(_min, _max):
                    raise argparse.ArgumentTypeError("{v} not in range [{min}-{max}].".format(v=i, min=_min, max=_max))
                return i
            except ValueError as va:
                pass
            if x not in _symbols:
                raise argparse.ArgumentTypeError("'{v}' must be one of {s}.".format(v=x, s=_symbols))
            return x

        return foo

    @classmethod
    def add_arguments(cls, parser, option_list):
        assert(len(option_list) > 0)
        options = DrbdOptions._options['options']
        for opt_key in option_list:
            option = options[opt_key]
            if opt_key in ['help', '_name']:
                continue
            if option['type'] == 'symbol':
                parser.add_argument('--' + opt_key, choices=option['symbols'])
            if option['type'] == 'boolean':
                parser.add_argument(
                    '--' + opt_key,
                    choices=['yes', 'no'],
                    help="yes/no (Default: %s)" % (option['default'])
                )
            if option['type'] == 'string':
                parser.add_argument('--' + opt_key)
            if option['type'] == 'numeric-or-symbol':
                min_ = int(option['min'])
                max_ = int(option['max'])
                parser.add_argument(
                    '--' + opt_key,
                    type=DrbdOptions.numeric_symbol(min_, max_, option['symbols']),
                    help="Integer between [{min}-{max}] or one of ['{syms}']".format(
                        min=min_,
                        max=max_,
                        syms="','".join(option['symbols'])
                    )
                )
            if option['type'] == 'numeric':
                min_ = option['min']
                max_ = option['max']
                default = option['default']
                if "unit" in option:
                    unit = "; Unit: " + option['unit']
                else:
                    unit = ""
                # sp.add_argument('--' + opt, type=rangecheck(min_, max_),
                #                 default=default, help="Range: [%d, %d]; Default: %d" %(min_, max_, default))
                # setting a default sets the option to != None, which makes
                # filterNew relatively complex
                parser.add_argument('--' + opt_key, type=rangecheck(min_, max_),
                                    help="Range: [%d, %d]; Default: %d%s" % (min_, max_, default, unit))
        for opt_key in option_list:
            if opt_key == 'help':
                continue
            else:
                parser.add_argument('--%s-%s' % (cls.unsetprefix, opt_key),
                                    action='store_true')

    def setup_commands(self, parser):
        resource_cmd = parser.add_parser(Commands.DRBD_RESOURCE_OPTIONS, description="Set drbd resource options.")
        resource_cmd.add_argument(
            'resource',
            type=namecheck(RES_NAME),
            help="Resource name"
        ).completer = self.resource_completer

        volume_cmd = parser.add_parser(Commands.DRBD_VOLUME_OPTIONS, description="Set drbd volume options.")
        volume_cmd.add_argument(
            'resource',
            type=namecheck(RES_NAME),
            help="Resource name"
        ).completer = self.resource_completer
        volume_cmd.add_argument(
            'volume_nr',
            type=int,
            help="Volume number"
        )

        resource_conn_cmd = parser.add_parser(
            Commands.DRBD_PEER_OPTIONS,
            description="Set drbd peer-device options."
        )
        resource_conn_cmd.add_argument(
            'resource',
            type=namecheck(RES_NAME),
            help="Resource name"
        ).completer = self.resource_completer
        resource_conn_cmd.add_argument(
            'node_a',
            type=namecheck(NODE_NAME),
            help="1. Node in the node connection"
        ).completer = self.node_completer
        resource_conn_cmd.add_argument(
            'node_b',
            type=namecheck(NODE_NAME),
            help="1. Node in the node connection"
        ).completer = self.node_completer

        options = DrbdOptions._options['options']
        self.add_arguments(resource_cmd, [x for x in options if x in DrbdOptions._options['filters']['resource']])
        self.add_arguments(volume_cmd, [x for x in options if x in DrbdOptions._options['filters']['volume']])
        self.add_arguments(resource_conn_cmd, [x for x in options if options[x]['category'] == 'peer-device-options'])

        resource_cmd.set_defaults(func=self._option_resource)
        volume_cmd.set_defaults(func=self._option_volume)
        resource_conn_cmd.set_defaults(func=self._option_resource_conn)

        return True

    @classmethod
    def filter_new(cls, args):
        """return a dict containing all non-None args"""
        return filter_new_args(cls.unsetprefix, args)

    @classmethod
    def parse_opts(cls, new_args):
        modify = {}
        deletes = []
        for arg in new_args:
            is_unset = arg.startswith(cls.unsetprefix)
            prop_name = arg[len(cls.unsetprefix) + 1:] if is_unset else arg
            category = cls._options['options'][prop_name]['category']

            namespace = cls._CategoyMap[category]
            key = namespace + '/' + prop_name
            if is_unset:
                deletes.append(key)
            else:
                modify[key] = new_args[arg]

        return modify, deletes

    def _option_resource(self, args):
        a = self.filter_new(args)
        del a['resource']  # remove resource name key

        mod_props, del_props = self._parse_opts(a)

        replies = self._linstor.resource_dfn_modify(
            args.resource,
            mod_props,
            del_props
        )
        return self.handle_replies(args, replies)

    def _option_volume(self, args):
        a = self.filter_new(args)
        del a['resource']  # remove volume name key
        del a['volume-nr']

        mod_props, del_props = self._parse_opts(a)

        replies = self._linstor.volume_dfn_modify(
            args.resource,
            args.volume_nr,
            mod_props,
            del_props
        )
        return self.handle_replies(args, replies)

    def _option_resource_conn(self, args):
        a = self.filter_new(args)
        del a['resource']
        del a['node-a']
        del a['node-b']

        mod_props, del_props = self.parse_opts(a)

        replies = self._linstor.resource_conn_modify(
            args.resource,
            args.node_a,
            args.node_b,
            mod_props,
            del_props
        )
        return self.handle_replies(args, replies)

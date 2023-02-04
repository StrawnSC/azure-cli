# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from azure.cli.core.azclierror import ArgumentUsageError


def validate_timeout_value(namespace):
    """Validates that zip deployment timeout is set to a reasonable min value"""
    if isinstance(namespace.timeout, int):
        if namespace.timeout <= 29:
            raise ArgumentUsageError('--timeout value should be a positive value in seconds and should be at least 30')


def validate_and_convert_to_int(flag, val):
    try:
        return int(val)
    except ValueError:
        raise ArgumentUsageError("{} is expected to have an int value.".format(flag))


def validate_range_of_int_flag(flag_name, value, min_val, max_val):
    value = validate_and_convert_to_int(flag_name, value)
    if min_val > value or value > max_val:
        raise ArgumentUsageError("Usage error: {} is expected to be between {} and {} (inclusive)".format(flag_name,
                                                                                                          min_val,
                                                                                                          max_val))
    return value

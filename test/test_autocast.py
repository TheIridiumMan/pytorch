# Owner(s): ["module: unknown"]

import collections
import unittest

import torch
from torch.testing._internal.autocast_test_lists import AutocastCPUTestLists
from torch.testing._internal.common_utils import (
    IS_WINDOWS,
    run_tests,
    skipIfTorchDynamo,
    TestCase,
)
from torch.utils._python_dispatch import TorchDispatchMode


class TestAutocastCPU(TestCase):
    def setUp(self):
        super().setUp()
        self.autocast_lists = AutocastCPUTestLists(torch.device("cpu"))

    def tearDown(self):
        del self.autocast_lists
        super().tearDown()

    def _run_autocast_outofplace(
        self,
        op,
        args,
        run_as_type,
        out_type=None,
        module=torch,
        add_kwargs=None,
        amp_dtype=torch.bfloat16,
    ):
        # helper to cast args
        def cast(val, to_type):
            if isinstance(val, torch.Tensor):
                return val.to(to_type) if val.is_floating_point() else val
            elif isinstance(val, collections.abc.Iterable):
                return type(val)(cast(v, to_type) for v in val)
            else:
                return val

        if add_kwargs is None:
            add_kwargs = {}

        self.assertFalse(torch.is_autocast_enabled(device_type="cpu"))
        with torch.amp.autocast(device_type="cpu", dtype=amp_dtype):
            self.assertTrue(torch.is_autocast_enabled(device_type="cpu"))
            out_type = out_type if out_type is not None else run_as_type
            output = output_method = None

            # Try module.* variant, if requested:
            if module is not None and hasattr(module, op):
                output = getattr(module, op)(*args, **add_kwargs)
                if isinstance(output, torch.Tensor):
                    self.assertTrue(
                        out_type == output.dtype,
                        f"autocast for torch.{op} produced {output.dtype}, should produce {out_type}",
                    )
            # Try Tensor.* variant:
            if hasattr(torch.Tensor, op):
                output_method = getattr(args[0], op)(*args[1:], **add_kwargs)
                if isinstance(output_method, torch.Tensor):
                    self.assertTrue(
                        out_type == output_method.dtype,
                        f"autocast for torch.{op} produced {output_method.dtype}, should produce torch.{out_type}",
                    )

            self.assertTrue(
                (output is not None) or (output_method is not None),
                f"{op} not found as an attribute on either Tensor or the requested module {module}",
            )

            # Accounts for ops that return Tensors, iterables, and other non-Tensors.
            # For example, lstm_cell returns a tuple and equal returns bool.
            def compare(first, second):
                if isinstance(first, torch.Tensor):
                    return torch.equal(first, second)
                elif isinstance(first, collections.abc.Iterable):
                    return all(compare(f, s) for f, s in zip(first, second))
                else:
                    return first == second

            # If both torch.* and Tensor.* variants were found, check outputs are identical
            if (output is not None) and (output_method is not None):
                self.assertTrue(type(output) == type(output_method))
                comparison = compare(output, output_method)
                self.assertTrue(
                    comparison, f"torch.{op} result did not match Tensor.{op} result"
                )

            # Compare numerics to Python-side "autocasting" that (we expect) does the same thing
            # as the C++-side autocasting, and should be bitwise accurate.
            output_to_compare = output if output is not None else output_method
            with torch.amp.autocast(device_type="cpu", enabled=False):
                self.assertFalse(torch.is_autocast_enabled(device_type="cpu"))

                if module is not None and hasattr(module, op):
                    control = getattr(module, op)(
                        *cast(args, run_as_type), **add_kwargs
                    )
                else:
                    control = getattr(args[0].to(run_as_type), op)(
                        *cast(args[1:], run_as_type), **add_kwargs
                    )
                self.assertTrue(type(output_to_compare) == type(control))
                comparison = compare(output_to_compare, control)
                self.assertTrue(comparison, f"torch.{op} result did not match control")
            self.assertTrue(torch.is_autocast_enabled(device_type="cpu"))
        self.assertFalse(torch.is_autocast_enabled(device_type="cpu"))

    def args_maybe_kwargs(self, op_with_args):
        if len(op_with_args) == 2:
            return op_with_args[0], op_with_args[1], {}
        else:
            return op_with_args[0], op_with_args[1], op_with_args[2]

    @skipIfTorchDynamo()
    def test_autocast_torch_expect_builtin_promote(self):
        for (
            op,
            args1,
            args2,
            out_type,
        ) in self.autocast_lists.torch_expect_builtin_promote:
            self._run_autocast_outofplace(op, args1, torch.float32, out_type=out_type)
            self._run_autocast_outofplace(
                op, args2, torch.float32, out_type=out_type, amp_dtype=torch.float16
            )

    @skipIfTorchDynamo()
    def test_autocast_methods_expect_builtin_promote(self):
        for (
            op,
            args1,
            args2,
            out_type,
        ) in self.autocast_lists.methods_expect_builtin_promote:
            self._run_autocast_outofplace(
                op, args1, torch.float32, module=None, out_type=out_type
            )
            self._run_autocast_outofplace(
                op,
                args2,
                torch.float32,
                module=None,
                out_type=out_type,
                amp_dtype=torch.float16,
            )

    @skipIfTorchDynamo()
    def test_autocast_torch_16(self):
        for op_with_args in self.autocast_lists.torch_16:
            op, args, maybe_kwargs = self.args_maybe_kwargs(op_with_args)
            self._run_autocast_outofplace(
                op, args, torch.bfloat16, add_kwargs=maybe_kwargs
            )
            self._run_autocast_outofplace(
                op,
                args,
                torch.float16,
                add_kwargs=maybe_kwargs,
                amp_dtype=torch.float16,
            )

    @skipIfTorchDynamo()
    def test_autocast_nn_16(self):
        for op_with_args in self.autocast_lists.nn_16:
            op, args, maybe_kwargs = self.args_maybe_kwargs(op_with_args)
            self._run_autocast_outofplace(
                op, args, torch.bfloat16, module=torch._C._nn, add_kwargs=maybe_kwargs
            )
            self._run_autocast_outofplace(
                op,
                args,
                torch.float16,
                module=torch._C._nn,
                add_kwargs=maybe_kwargs,
                amp_dtype=torch.float16,
            )

    @skipIfTorchDynamo()
    def test_autocast_torch_fp32(self):
        for op_with_args in self.autocast_lists.torch_fp32:
            op, args, maybe_kwargs = self.args_maybe_kwargs(op_with_args)
            self._run_autocast_outofplace(
                op, args, torch.float32, add_kwargs=maybe_kwargs
            )
            self._run_autocast_outofplace(
                op,
                args,
                torch.float32,
                add_kwargs=maybe_kwargs,
                amp_dtype=torch.float16,
            )

    @skipIfTorchDynamo()
    def test_autocast_nn_fp32(self):
        for op_with_args in self.autocast_lists.nn_fp32:
            op, args, maybe_kwargs = self.args_maybe_kwargs(op_with_args)
            self._run_autocast_outofplace(
                op, args, torch.float32, module=torch._C._nn, add_kwargs=maybe_kwargs
            )
            self._run_autocast_outofplace(
                op,
                args,
                torch.float32,
                module=torch._C._nn,
                add_kwargs=maybe_kwargs,
                amp_dtype=torch.float16,
            )

    @skipIfTorchDynamo()
    def test_autocast_torch_need_autocast_promote(self):
        for op, args1, args2 in self.autocast_lists.torch_need_autocast_promote:
            self._run_autocast_outofplace(op, args1, torch.float32)
            self._run_autocast_outofplace(
                op, args2, torch.float32, amp_dtype=torch.float16
            )

    @unittest.skipIf(IS_WINDOWS, "Limit support for bf16 path")
    def test_autocast_rnn(self):
        if (
            torch.backends.mkldnn.is_available()
            and torch.ops.mkldnn._is_mkldnn_bf16_supported()
        ):
            x = torch.randn(1, 2, 1)
            hx = torch.randn(2, 2, 1)
            cx = torch.randn(2, 2, 1)

            m = torch.nn.LSTM(1, 1, 2).to(torch.bfloat16)

            # Raise ValueError when autocast is not enabled
            with self.assertRaisesRegex(ValueError, "input must have the type"):
                m(x, (hx, cx))

            # Should be able to run the below case with autocast
            with torch.amp.autocast(device_type="cpu"):
                m(x, (hx, cx))

    def test_autocast_disabled_with_fp32_dtype(self):
        with torch.autocast(device_type="cpu", dtype=torch.float32, enabled=False):
            _ = torch.ones(10)

    def test_generic_autocast(self):
        for op_with_args in self.autocast_lists.torch_16:
            op, args, maybe_kwargs = self.args_maybe_kwargs(op_with_args)
            with torch.amp.autocast(device_type="cpu"):
                generic_autocast_output = getattr(torch, op)(*args, **maybe_kwargs)
            with torch.amp.autocast(device_type="cpu"):
                cpu_autocast_output = getattr(torch, op)(*args, **maybe_kwargs)
            self.assertEqual(generic_autocast_output, cpu_autocast_output)

    def test_cpu_autocast_deprecated_warning(self):
        with self.assertWarnsRegex(
            FutureWarning,
            r"`torch.cpu.amp.autocast\(args...\)` is deprecated. Please use `torch.amp.autocast\('cpu', args...\)` instead.",
        ):
            with torch.cpu.amp.autocast():
                _ = torch.ones(10)


class CustomLinear(torch.autograd.Function):
    @staticmethod
    def forward(ctx, x, w_t):
        ctx.save_for_backward(x, w_t)
        return torch.nn.functional.linear(x, w_t)

    @staticmethod
    def backward(ctx, grad_output):
        x, w_t = ctx.saved_tensors
        with torch.autocast(device_type="cuda"):
            dL_dX = torch.matmul(grad_output, w_t)
            dL_dW = torch.matmul(x.transpose(0, 1), grad_output).transpose(0, 1)
        return dL_dX, dL_dW


class WeightDTypeCastCounterMode(TorchDispatchMode):
    def __init__(self, weight):
        super().__init__()
        self.dtype_cast_counter = 0
        self.weight = weight

    def __torch_dispatch__(self, func, types, args=(), kwargs=None):
        if (
            func is torch.ops.aten._to_copy.default
            and args[0] is self.weight
            and kwargs["dtype"] is torch.float16
        ):
            self.dtype_cast_counter += 1
        return func(*args, **kwargs)

    def __enter__(self):
        self.old_clear_cache = torch.clear_autocast_cache
        torch.clear_autocast_cache = lambda: None
        return super().__enter__()

    def __exit__(self, exc_type, exc_val, exc_tb):
        torch.clear_autocast_cache = self.old_clear_cache
        return super().__exit__(exc_type, exc_val, exc_tb)


@unittest.skipIf(not torch.cuda.is_available(), "requires cuda")
class TestAutocastGPU(TestCase):
    def test_cast_cache_is_global(self):
        """
        Verifies that the autocast cache is global. This is done by
        mocking out cache clearing at the end of the forward pass,
        running forward+backward with an explicit call to autocast in the
        backward, and verifying that the weight only get cast to float16 once.
        """

        data = torch.randn(2, 3).cuda()
        weight = torch.nn.Parameter(torch.randn(4, 3).cuda())

        with WeightDTypeCastCounterMode(weight) as mode:
            with torch.autocast(device_type="cuda"):
                output = CustomLinear.apply(data, weight)
                s = output.sum()
            s.backward()

        self.assertEqual(mode.dtype_cast_counter, 1)

    def test_cache_disabled(self):
        data = torch.randn(2, 3).cuda()
        weight = torch.nn.Parameter(torch.randn(4, 3).cuda())

        try:
            torch._C._set_cached_tensors_enabled(True)
            torch._C._add_cached_tensor(weight)

            with WeightDTypeCastCounterMode(weight) as mode:
                with torch.autocast(device_type="cuda"):
                    output = CustomLinear.apply(data, weight)
                    s = output.sum()
                s.backward()

            # we should not have cached the conversion of the weight
            self.assertEqual(mode.dtype_cast_counter, 2)

        finally:
            torch._C._set_cached_tensors_enabled(False)


class TestTorchAutocast(TestCase):
    def test_autocast_fast_dtype(self):
        gpu_fast_dtype = torch.get_autocast_dtype(device_type="cuda")
        cpu_fast_dtype = torch.get_autocast_dtype(device_type="cpu")
        self.assertEqual(gpu_fast_dtype, torch.half)
        self.assertEqual(cpu_fast_dtype, torch.bfloat16)

    def test_invalid_device(self):
        dev = "not a real device"
        msg = f"Invalid device string: '{dev}'"
        with self.assertRaisesRegex(RuntimeError, msg):
            with torch.autocast(device_type=dev):
                _ = torch.tensor(1)
        with self.assertRaisesRegex(RuntimeError, msg):
            assert torch.amp.is_autocast_available(device_type=dev)

    def test_non_string_device(self):
        """Test that `autocast` throws a ValueError when provided a `torch.device` object for `device_type` instead of a string"""
        dev = torch.device("cpu")
        msg = f"Expected `device_type` of type `str`, got: `{type(dev)}`"
        with self.assertRaisesRegex(expected_exception=ValueError, expected_regex=msg):
            torch.autocast(device_type=dev)


if __name__ == "__main__":
    run_tests()

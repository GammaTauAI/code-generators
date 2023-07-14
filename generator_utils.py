from .model import ModelBase
import random

from typing import Union, List, Optional, Callable


def get_code_from_possible_markdown(markdown: str) -> str:
    if not "```" in markdown:
        return markdown

    # get the code by stripping out markdown ``` and ```
    out_lines = markdown.split("\n")
    in_func = False
    func_lines = []
    for line in out_lines:
        if "```" in line:
            if in_func:
                in_func = False
                break
            else:
                in_func = True
                continue
        if in_func:
            func_lines.append(line)

    return "\n".join(func_lines)


def remove_func_sig_if_present(func_sig: str, func_body: str) -> str:
    if func_sig in func_body:
        # remove the entire line
        lines = func_body.split("\n")
        lines = [line for line in lines if func_sig not in line]
    else:
        return func_body


def generic_generate_func_impl(
    func_sig: str,
    model: ModelBase,
    strategy: str,
    prev_func_impl,
    feedback,
    self_reflection,
    num_comps,
    temperature,
    REFLEXION_CHAT_INSTRUCTION: str,
    REFLEXION_FEW_SHOT: str,
    SIMPLE_CHAT_INSTRUCTION: str,
    REFLEXION_COMPLETION_INSTRUCTION: str,
    SIMPLE_COMPLETION_INSTRUCTION: str,
    fix_body: Callable[[str], str]
) -> Union[str, List[str]]:
    if strategy != "reflexion" and strategy != "simple":
        raise ValueError(
            f"Invalid strategy: given `{strategy}` but expected one of `reflexion` or `simple`")
    if strategy == "reflexion" and (prev_func_impl is None or feedback is None or self_reflection is None):
        raise ValueError(
            f"Invalid arguments: given `strategy=reflexion` but `prev_func_impl`, `feedback`, or `self_reflection` is None")

    if model.is_chat:
        if strategy == "reflexion":
            message = f"{REFLEXION_FEW_SHOT}\n[previous impl]:\n{prev_func_impl}\n\n[unit test results from previous impl]:\n{feedback}\n\n[reflection on previous impl]:\n{self_reflection}\n\n[improved impl]:\n{func_sig}"
            # func_bodies is a really bad name, as it can also be just 1 string
            print('----------------------- SYSTEM MESSAGE -----------------------')
            print(REFLEXION_CHAT_INSTRUCTION)
            print('----------------------------------------------')
            print(' ----------------------- USER MESSAGE -----------------------')
            print(message, flush=True)
            print('----------------------------------------------')
            func_bodies = model.generate_chat(REFLEXION_CHAT_INSTRUCTION,
                                              message, num_comps=num_comps, temperature=temperature)
        else:
            print('----------------------- SYSTEM MESSAGE -----------------------')
            print(SIMPLE_CHAT_INSTRUCTION)
            print('----------------------------------------------')
            print(' ----------------------- USER MESSAGE -----------------------')
            print(func_sig, flush=True)
            print('----------------------------------------------')
            func_bodies = model.generate_chat(SIMPLE_CHAT_INSTRUCTION if strategy ==
                                              "simple" else REFLEXION_CHAT_INSTRUCTION, func_sig, num_comps=num_comps, temperature=temperature)
    else:
        if strategy == "reflexion":
            prompt = f"{REFLEXION_COMPLETION_INSTRUCTION}\n{prev_func_impl}\n\nunit tests:\n{feedback}\n\nhint:\n{self_reflection}\n\n# improved implementation\n{func_sig}"
            func_bodies = model.generate(
                prompt, num_comps=num_comps, temperature=temperature)
        else:
            prompt = f"{SIMPLE_COMPLETION_INSTRUCTION}\n{func_sig}"
            func_bodies = model.generate(
                prompt, num_comps=num_comps, temperature=temperature)

    def fix_code(code):
        return fix_body(remove_func_sig_if_present(
            func_sig, get_code_from_possible_markdown(code)))

    if num_comps == 1:
        assert isinstance(func_bodies, str)
        code = func_sig + fix_code(func_bodies)
        print('--------------------- GENERATED FUNC BODY ---------------------')
        print(code)
        print('------------------------------------------')
        return code

    else:
        print('--------------------- GENERATED FUNC BODY ---------------------')
        codes = [func_sig + fix_code(body) for body in func_bodies]
        print(codes)
        print('------------------------------------------')
        return codes


def generic_generate_internal_tests(
        func_sig: str,
        model: ModelBase,
        committee_size: int,
        max_num_tests: int,
        TEST_GENERATION_FEW_SHOT: str,
        TEST_GENERATION_CHAT_INSTRUCTION: str,
        TEST_GENERATION_COMPLETION_INSTRUCTION: str,
        parse_tests: Callable[[str], List[str]],
        is_syntax_valid: Callable[[str], bool],
        is_react: bool = False
) -> List[str]:
    """
    Generates tests for a function using a refinement technique with the number
    of specified commmittee members.
    """
    if model.is_chat:
        if is_react:
            message = f'{TEST_GENERATION_FEW_SHOT}\n\n[func signature]:\n{func_sig}\n\n[think]:'
            output = model.generate_chat(
                TEST_GENERATION_CHAT_INSTRUCTION, message, max_tokens=1024)
            print(f'React test generation output: {output}')
        else:
            message = f'{TEST_GENERATION_FEW_SHOT}\n\nfunc signature:\n{func_sig}\nunit tests:'
            output = model.generate_chat(
                TEST_GENERATION_CHAT_INSTRUCTION, message, max_tokens=1024)
    else:
        prompt = f'{TEST_GENERATION_COMPLETION_INSTRUCTION}\n\nfunc signature:\n{func_sig}\nunit tests:'
        output = model.generate(prompt, max_tokens=1024)
    all_tests = parse_tests(output)  # type: ignore
    valid_tests = [test for test in all_tests if is_syntax_valid(test)]

    return sample_n_random(valid_tests, max_num_tests)


def generic_generate_self_reflection(
        func: str,
        feedback: str,
        model: ModelBase,
        SELF_REFLECTION_CHAT_INSTRUCTION: str,
        SELF_REFLECTION_COMPLETION_INSTRUCTION: str,
        SELF_REFLECTION_FEW_SHOT: Optional[str] = None
) -> str:
    if model.is_chat:
        if SELF_REFLECTION_FEW_SHOT is not None:
            reflection = model.generate_chat(
                SELF_REFLECTION_CHAT_INSTRUCTION,
                f'{SELF_REFLECTION_FEW_SHOT}\n\n[function impl]:\n{func}\n\n[unit test results]:\n{feedback}\n\n[self-reflection]:')
            print(f'Self reflection output: {reflection}')
        else:
            reflection = model.generate_chat(
                SELF_REFLECTION_CHAT_INSTRUCTION,
                f'Function implementation:\n{func}\n\nUnit test results:\n{feedback}\n\nSelf-reflection:')
    else:
        reflection = model.generate(
            f'{SELF_REFLECTION_COMPLETION_INSTRUCTION}\n{func}\n\n{feedback}\n\nExplanation:')
    return reflection  # type: ignore


def sample_n_random(items: List[str], n: int) -> List[str]:
    """Sample min(n, len(items)) random items from a list"""
    assert n >= 0
    if n >= len(items):
        return items
    return random.sample(items, n)

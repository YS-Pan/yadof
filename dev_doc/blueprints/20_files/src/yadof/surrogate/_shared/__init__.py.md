# File blueprint: src/yadof/surrogate/_shared/__init__.py

Mark the private shared-primitive package. It has no eager imports so parent
surrogate imports remain lightweight and optional numerical dependencies stay lazy.

from __future__ import annotations
_AQ='\x1b[1;34m'
_AP='\x1b[1;33m'
_AO='\x1b[1;32m'
_AN='No usages found.'
_AM='entrypoint'
_AL='expression_statement'
_AK='source_file'
_AJ='interface'
_AI='variable_declarator'
_AH='lexical_declaration'
_AG='const_item'
_AF='const_spec'
_AE='type_spec'
_AD='generator_function_declaration'
_AC=b'__main__'
_AB='condition'
_AA='tree_sitter_yaml'
_A9='tree_sitter_bash'
_A8='tree_sitter_elixir'
_A7='tree_sitter_cpp'
_A6='tree_sitter_c'
_A5='tree_sitter_typescript'
_A4='tree_sitter_javascript'
_A3='object'
_A2='program'
_A1='const'
_A0='class'
_z='method'
_y='impl_item'
_x='enum_declaration'
_w='enum_item'
_v='struct_item'
_u='trait_item'
_t='type_declaration'
_s='class_definition'
_r='method_declaration'
_q='function_item'
_p='function_definition'
_o='if_statement'
_n=b'\r'
_m=b'\r\n'
_l='left'
_k='.sh'
_j='.ex'
_i='.hs'
_h='.kt'
_g='.rb'
_f='.cs'
_e='.cpp'
_d='.jsx'
_c='export'
_b='interface_declaration'
_a='definition'
_Z='identifier'
_Y='.tsx'
_X='\n'
_W='type'
_V='function'
_U='replace'
_T='utf-8'
_S='assignment'
_R='\x1b[1;35m'
_Q='class_declaration'
_P='function_declaration'
_O='export_statement'
_N='reference'
_M='.java'
_L='.ts'
_K='.js'
_J='variable'
_I='.go'
_H=b'\n'
_G='name'
_F='.rs'
_E=True
_D='.py'
_C=False
_B='language'
_A=None
import argparse,importlib,json,sys
from collections import defaultdict
from dataclasses import asdict,dataclass,field
from enum import Enum
from pathlib import Path
from typing import IO,Iterator
from tree_sitter import Language,Parser,Query,QueryCursor
class Capability(str,Enum):FULL='full';PARTIAL='partial';NONE='none'
CAP_ORDER={Capability.FULL:2,Capability.PARTIAL:1,Capability.NONE:0}
EXT_TO_LANG_PKG={_D:('tree_sitter_python',_B),_K:(_A4,_B),_d:(_A4,_B),_L:(_A5,'language_typescript'),_Y:(_A5,'language_tsx'),_I:('tree_sitter_go',_B),_F:('tree_sitter_rust',_B),_M:('tree_sitter_java',_B),'.c':(_A6,_B),'.h':(_A6,_B),_e:(_A7,_B),'.cc':(_A7,_B),_f:('tree_sitter_c_sharp',_B),_g:('tree_sitter_ruby',_B),'.php':('tree_sitter_php','language_php'),'.swift':('tree_sitter_swift',_B),_h:('tree_sitter_kotlin',_B),'.lua':('tree_sitter_lua',_B),_i:('tree_sitter_haskell',_B),_j:(_A8,_B),'.exs':(_A8,_B),'.r':('tree_sitter_r',_B),_k:(_A9,_B),'.bash':(_A9,_B),'.toml':('tree_sitter_toml',_B),'.yaml':(_AA,_B),'.yml':(_AA,_B),'.css':('tree_sitter_css',_B),'.html':('tree_sitter_html',_B),'.sql':('tree_sitter_sql',_B)}
LANG_NAME_TO_EXT={'python':_D,'py':_D,'javascript':_K,'js':_K,'typescript':_L,'ts':_L,'tsx':_Y,'go':_I,'rust':_F,'rs':_F,'java':_M,'c':'.c','cpp':_e,'c++':_e,'csharp':_f,'cs':_f,'ruby':_g,'rb':_g,'php':'.php','swift':'.swift','kotlin':_h,'kt':_h,'lua':'.lua','haskell':_i,'hs':_i,'elixir':_j,'ex':_j,'r':'.r','bash':_k,'sh':_k,'toml':'.toml','yaml':'.yaml','css':'.css','html':'.html','sql':'.sql'}
_lang_cache={}
_parser_cache={}
_query_cache={}
_generic_cache={}
_lang_load_errors={}
def _load_language(ext,warn=_C):
	A=ext
	if A in _lang_cache:return _lang_cache[A]
	B=EXT_TO_LANG_PKG.get(A)
	if not B:return
	E,F=B
	try:G=importlib.import_module(E);C=Language(getattr(G,F)());_lang_cache[A]=C;return C
	except Exception as D:
		_lang_load_errors[A]=str(D)
		if warn:print(f"warning: could not load grammar for {A!r}: {D}",file=sys.stderr)
		return
def _get_parser(ext,lang):
	B=ext,id(lang);A=_parser_cache.get(B)
	if A is _A:A=Parser(lang);_parser_cache[B]=A
	return A
def _get_query(ext,lang,src):
	B=ext,src;A=_query_cache.get(B)
	if A is _A:
		try:A=Query(lang,src)
		except Exception:return
		_query_cache[B]=A
	return A
_CANDIDATE_ID_TYPES=[_Z,'type_identifier','field_identifier','property_identifier','variable_name',_G]
def _build_generic_query(ext,lang):
	A=ext
	if A in _generic_cache:return _generic_cache[A]
	B=[B for B in _CANDIDATE_ID_TYPES if _get_query(A,lang,f"({B}) @x")is not _A]
	if not B:_generic_cache[A]=_A;return
	C=f"({B[0]}) @reference.name"if len(B)==1 else'[\n '+'\n '.join(f"({A})"for A in B)+'\n] @reference.name';_generic_cache[A]=C;return C
_PYTHON_QUERIES='\n(function_definition    name: (identifier) @definition.name) @definition.node\n(class_definition       name: (identifier) @definition.name) @definition.node\n(assignment             left: (_) @assignment.name) @assignment.node\n(augmented_assignment   left: (identifier) @assignment.name) @assignment.node\n(named_expression       name: (identifier) @assignment.name) @assignment.node\n(call                   function: (identifier) @call.name) @call.node\n(call                   function: (attribute attribute: (identifier) @call.name)) @call.node\n(decorator              (identifier) @call.name) @call.node\n(decorator              (call function: (identifier) @call.name)) @call.node\n(import_statement       (dotted_name (identifier) @import.name)) @import.node\n(import_from_statement  (dotted_name (identifier) @import.name)) @import.node\n(import_from_statement  (aliased_import name: (dotted_name (identifier) @import.name))) @import.node\n(aliased_import         alias: (identifier) @import.name) @import.node\n(identifier) @reference.name\n'
_JS_QUERIES_BASE='\n(function_declaration      name: (identifier) @definition.name) @definition.node\n(method_definition         name: (property_identifier) @definition.name) @definition.node\n(class_declaration         name: (identifier) @definition.name) @definition.node\n(generator_function_declaration name: (identifier) @definition.name) @definition.node\n(variable_declarator       name: (_) @assignment.name) @assignment.node\n(assignment_expression     left: (identifier) @assignment.name) @assignment.node\n(call_expression           function: (identifier) @call.name) @call.node\n(call_expression           function: (member_expression property: (property_identifier) @call.name)) @call.node\n(new_expression            constructor: (identifier) @call.name) @call.node\n(import_clause             (identifier) @import.name) @import.node\n(import_specifier          name: (identifier) @import.name) @import.node\n(identifier) @reference.name\n'
_JS_QUERIES=_JS_QUERIES_BASE
_TS_QUERIES=_JS_QUERIES_BASE+'\n(class_declaration         name: (type_identifier) @definition.name) @definition.node\n(interface_declaration     name: (type_identifier) @definition.name) @definition.node\n(type_alias_declaration    name: (type_identifier) @definition.name) @definition.node\n(enum_declaration          name: (identifier) @definition.name) @definition.node\n(type_identifier) @reference.name\n'
_GO_QUERIES='\n(function_declaration  name: (identifier) @definition.name) @definition.node\n(method_declaration    name: (field_identifier) @definition.name) @definition.node\n(type_spec             name: (type_identifier) @definition.name) @definition.node\n(short_var_declaration left: (expression_list (identifier) @assignment.name)) @assignment.node\n(var_spec              name: (identifier) @assignment.name) @assignment.node\n(const_spec            name: (identifier) @assignment.name) @assignment.node\n(call_expression       function: (identifier) @call.name) @call.node\n(call_expression       function: (selector_expression field: (field_identifier) @call.name)) @call.node\n(identifier) @reference.name\n(type_identifier) @reference.name\n(field_identifier) @reference.name\n'
_RUST_QUERIES='\n(function_item    name: (identifier) @definition.name) @definition.node\n(struct_item      name: (type_identifier) @definition.name) @definition.node\n(enum_item        name: (type_identifier) @definition.name) @definition.node\n(trait_item       name: (type_identifier) @definition.name) @definition.node\n(impl_item        type: (type_identifier) @definition.name) @definition.node\n(let_declaration  pattern: (identifier) @assignment.name) @assignment.node\n(call_expression  function: (identifier) @call.name) @call.node\n(call_expression  function: (field_expression field: (field_identifier) @call.name)) @call.node\n(call_expression  function: (scoped_identifier name: (identifier) @call.name)) @call.node\n(use_declaration  argument: (identifier) @import.name) @import.node\n(identifier) @reference.name\n(type_identifier) @reference.name\n'
_JAVA_QUERIES='\n(method_declaration    name: (identifier) @definition.name) @definition.node\n(class_declaration     name: (identifier) @definition.name) @definition.node\n(interface_declaration name: (identifier) @definition.name) @definition.node\n(enum_declaration      name: (identifier) @definition.name) @definition.node\n(variable_declarator   name: (identifier) @assignment.name) @assignment.node\n(method_invocation     name: (identifier) @call.name) @call.node\n(object_creation_expression type: (type_identifier) @call.name) @call.node\n(import_declaration    (scoped_identifier name: (identifier) @import.name)) @import.node\n(identifier) @reference.name\n(type_identifier) @reference.name\n'
LANG_QUERIES={_D:_PYTHON_QUERIES,_K:_JS_QUERIES,_d:_JS_QUERIES,_L:_TS_QUERIES,_Y:_TS_QUERIES,_I:_GO_QUERIES,_F:_RUST_QUERIES,_M:_JAVA_QUERIES}
KIND_PRIORITY=[_a,_S,'call','import',_N]
VALID_KINDS=KIND_PRIORITY
_PY_EXTS=frozenset({_D})
_JS_EXTS=frozenset({_K,_d,_L,_Y})
_PY_SKIP=frozenset({',','(',')','[',']','*','**',':'})
def _extract_py_bindings(node):
	A=node
	if A.type==_Z:return[A]
	if A.type=='list_splat_pattern':return[A for A in A.children if A.type==_Z]
	return[B for A in A.children if A.type not in _PY_SKIP for B in _extract_py_bindings(A)]
_JS_BINDING_TYPES=frozenset({_Z,'shorthand_property_identifier_pattern'})
_JS_SKIP=frozenset({',','[',']','{','}','...','=',':','(',')'})
def _extract_js_bindings(node):
	A=node
	if A.type in _JS_BINDING_TYPES:return[A]
	if A.type=='pair_pattern':B=A.child_by_field_name('value');return _extract_js_bindings(B)if B else[]
	if A.type=='assignment_pattern':C=A.child_by_field_name(_l);return _extract_js_bindings(C)if C else[]
	return[B for A in A.children if A.type not in _JS_SKIP for B in _extract_js_bindings(A)]
def _read_context(source,line,n_lines=2):A=n_lines;C=source.replace(_m,_H).replace(_n,_H);B=C.split(_H);D=max(0,line-A-1);E=min(len(B),line+A);return _H.join(B[D:E]).decode(_T,errors=_U)
@dataclass
class OutlineItem:
	kind:str;name:str;file:str;start_line:int;start_col:int;end_line:int;end_col:int;exported:bool;entry_point:bool;context:str=field(default='')
	def as_dict(A):return asdict(A)
def _is_exported(node,ext,name):
	C=node;B=name;A=ext
	if A in _JS_EXTS:return C.parent is not _A and C.parent.type==_O
	if A==_I:return bool(B)and B[0].isupper()
	if A==_F:
		for D in C.children:
			if D.type=='visibility_modifier':return D.text.strip()==b'pub'
		return _C
	if A==_D:return bool(B)and not B.startswith('_')
	return _C
def _is_entry_point(node,ext,name):
	D='main';C=name;B=ext;A=node
	if B==_D:
		if C==D:return _E
		if A.type==_o:E=A.child_by_field_name(_AB);return E is not _A and _AC in E.text
		return _C
	if B==_I:return C in(D,'init')
	if B in _JS_EXTS:return C in(D,'default')or A.parent is not _A and A.parent.type==_O and b'default'in A.parent.text
	if B==_F:return C==D
	if B==_M:return C==D
	return _C
def _node_kind(node_type):A=node_type;B={_p:_V,_P:_V,_q:_V,_AD:_V,'method_definition':_z,_r:_z,_s:_A0,_Q:_A0,_b:_AJ,'type_alias_declaration':_W,_AE:_W,_t:_W,_u:'trait',_v:'struct',_w:'enum',_x:'enum',_y:'impl',_S:_J,'var_spec':_J,_AF:_A1,_AG:_A1,_AH:_J,_AI:_J,_O:_c,_o:'block'};return B.get(A,A)
_CONTAINER_TYPES={_D:frozenset({'module',_s,_p}),_K:frozenset({_A2,_Q,_P,_A3,_O}),_L:frozenset({_A2,_Q,_P,_b,_A3,_O}),_I:frozenset({_AK,_t,_P}),_F:frozenset({_AK,'mod_item',_y,_u,_v,_w,_q}),_M:frozenset({_A2,_Q,_b,_x})}
def _outline_file(path,max_depth=1,lang_ext=_A,include_context=_C):
	D=path;A=(lang_ext or D.suffix).lower();C=_load_language(A)
	if C is _A:return[]
	F=D.read_bytes();H=_get_parser(A,C).parse(F);I=H.root_node;J=_CONTAINER_TYPES.get(A,frozenset());E=[]
	def K(def_node,name_node_or_str,*,override_kind=_A):
		E=name_node_or_str;B=def_node;C=E.text.decode(_T,errors=_U)if hasattr(E,'text')else E
		if not C:return
		H=override_kind or _node_kind(B.type);G=''
		if include_context:G=_read_context(F,B.start_point.row+1)
		return OutlineItem(kind=H,name=C,file=str(D),start_line=B.start_point.row+1,start_col=B.start_point.column,end_line=B.end_point.row+1,end_col=B.end_point.column,exported=_is_exported(B,A,C),entry_point=_is_entry_point(B,A,C),context=G)
	if A==_D:B=_handle_py_node
	elif A in _JS_EXTS:B=_handle_js_node
	elif A==_I:B=_handle_go_node
	elif A==_F:B=_handle_rs_node
	elif A==_M:B=_handle_java_node
	else:B=_A
	def G(node,depth):
		C=depth
		if C>max_depth:return
		for A in node.children:
			if not A.is_named:continue
			if B:
				D=B(A,K)
				if D:E.extend(D)
			if A.type in J:G(A,C+1)
	G(I,0);return E
def _handle_py_node(node,make_item):
	D=make_item;A=node;C=[]
	if A.type in(_p,_s):
		F=A.child_by_field_name(_G)
		if F:
			B=D(A,F)
			if B:C.append(B)
	elif A.type==_AL:
		E=next((A for A in A.children if A.type==_S),_A)
		if E:
			G=E.child_by_field_name(_l)
			if G:
				for I in _extract_py_bindings(G):
					B=D(E,I,override_kind=_J)
					if B:C.append(B)
	elif A.type==_o:
		H=A.child_by_field_name(_AB)
		if H is not _A and _AC in H.text:
			B=D(A,'__main__',override_kind=_AM)
			if B:C.append(B)
	return C
def _handle_js_node(node,make_item):
	D=make_item;A=node;C=[]
	if A.type==_O:
		for F in A.children:
			if F.is_named and F.type not in(_c,'default','from'):C.extend(_handle_js_node(F,D))
	elif A.type in(_P,_AD,_Q):
		I=A.child_by_field_name(_G)
		if I:
			B=D(A,I)
			if B:C.append(B)
	elif A.type==_AH:
		for G in A.children:
			if G.type!=_AI:continue
			J=G.child_by_field_name(_G)
			if J:
				for M in _extract_js_bindings(J):
					B=D(G,M,override_kind=_J)
					if B:C.append(B)
	elif A.type==_AL:
		H=next((A for A in A.children if A.type=='assignment_expression'),_A)
		if H:
			E=H.child_by_field_name(_l)
			if E and E.type=='member_expression':
				K=E.child_by_field_name(_A3)
				if K is not _A and K.text==b'module':
					L=E.child_by_field_name('property')
					if L is not _A and L.text==b'exports':
						B=D(H,'module.exports',override_kind=_c)
						if B:C.append(B)
	return C
def _handle_go_node(node,make_item):
	F=make_item;A=node;D=[]
	if A.type in(_P,_r):
		B=A.child_by_field_name(_G)
		if B:
			C=F(A,B)
			if C:D.append(C)
	elif A.type in('var_declaration','const_declaration',_t):
		for E in A.children:
			if E.type in('var_spec',_AF,_AE):
				B=E.child_by_field_name(_G)
				if B:
					C=F(E,B)
					if C:D.append(C)
	return D
def _handle_rs_node(node,make_item):
	A=node;B=[]
	if A.type in(_q,_v,_w,_u,_y,_AG):
		C=A.child_by_field_name(_G)or A.child_by_field_name(_W)
		if C:
			D=make_item(A,C)
			if D:B.append(D)
	return B
def _handle_java_node(node,make_item):
	A=node;B=[]
	if A.type in(_Q,_b,_x,_r):
		C=A.child_by_field_name(_G)
		if C:
			D=make_item(A,C)
			if D:B.append(D)
	return B
def outline_path(path,lang_ext=_A,extensions=_A,max_depth=1,include_context=_C):
	D=lang_ext;A=path
	if D is not _A:
		def E(p):return _E
	else:
		F=extensions or set(EXT_TO_LANG_PKG.keys())
		def E(p):return p.suffix.lower()in F
	G=sorted(A.rglob('*'))if A.is_dir()else[A];B=[]
	for C in G:
		if not C.is_file()or not E(C):continue
		B.extend(_outline_file(C,max_depth,D,include_context))
	B.sort(key=lambda i:(i.file,i.start_line));return B
@dataclass
class SymbolUsage:
	symbol:str;kind:str;capability:Capability;file:str;name_line:int;name_col:int;start_line:int;start_col:int;end_line:int;end_col:int;context:str=field(default='')
	def as_dict(A):B=asdict(A);B['capability']=A.capability.value;return B
def _find_outer(name_node,outer_map):
	C=outer_map;B=name_node;G=B.start_byte;H=B.end_byte;D,E=_A,float('inf');A=B.parent
	while A is not _A:
		if A.id in C:
			if A.start_byte<=G and A.end_byte>=H:
				F=A.end_byte-A.start_byte
				if F<E:D,E=C[A.id],F;break
		A=A.parent
	return D
class SymbolFinder:
	def __init__(A,symbols,include_references=_E,include_context=_C):
		B=symbols;A.symbols=B;A.include_references=include_references;A.include_context=include_context;A.base_to_orig=defaultdict(list)
		for C in B:D=C.split('.')[-1];A.base_to_orig[D].append(C)
		A._sym_set=frozenset(A.base_to_orig.keys())
	def search_file(C,path,lang_ext=_A):
		O=path;D=(lang_ext or O.suffix).lower();G=_load_language(D)
		if G is _A:return{A:[]for A in C.symbols},Capability.NONE
		Q=LANG_QUERIES.get(D);P=Capability.FULL;K=_get_query(D,G,Q)if Q else _A
		if K is _A:
			R=_build_generic_query(D,G)
			if not R:return{A:[]for A in C.symbols},Capability.NONE
			K=_get_query(D,G,R);P=Capability.PARTIAL
			if K is _A:return{A:[]for A in C.symbols},Capability.NONE
		S=O.read_bytes();b=_get_parser(D,G).parse(S);H=QueryCursor(K).captures(b.root_node);T=set();U={}
		for A in KIND_PRIORITY:
			if A==_N:continue
			V=f"{A}.node"
			if V in H:
				for I in H[V]:U.setdefault(A,{})[I.id]=I
			J=f"{A}.name"
			if J in H:
				for I in H[J]:T.add((I.start_byte,I.end_byte))
		W=defaultdict(list)
		for(J,c)in H.items():
			if not J.endswith('.name'):continue
			A=J[:-5]
			if A not in KIND_PRIORITY:continue
			if A==_N and not C.include_references:continue
			for E in c:
				if A==_N:
					if(E.start_byte,E.end_byte)in T:continue
				if A==_S:
					if D in _PY_EXTS:L=_extract_py_bindings(E)
					elif D in _JS_EXTS:L=_extract_js_bindings(E)
					else:L=[E]
				else:L=[E]
				for F in L:
					M=F.text.decode(_T,errors=_U)
					if M not in C._sym_set:continue
					d=U.get(A,{});X=_find_outer(F,d);N=X if X else F;Y=''
					if C.include_context:Y=_read_context(S,F.start_point.row+1)
					W[M].append(SymbolUsage(symbol='',kind=A,capability=P,file=str(O),name_line=F.start_point.row+1,name_col=F.start_point.column,start_line=N.start_point.row+1,start_col=N.start_point.column,end_line=N.end_point.row+1,end_col=N.end_point.column,context=Y))
		Z={A:[]for A in C.symbols}
		for(M,e)in W.items():
			for a in C.base_to_orig[M]:
				for B in e:Z[a].append(SymbolUsage(symbol=a,kind=B.kind,capability=B.capability,file=B.file,name_line=B.name_line,name_col=B.name_col,start_line=B.start_line,start_col=B.start_col,end_line=B.end_line,end_col=B.end_col,context=B.context))
		return Z,P
def search_symbols(symbols,path,lang_ext=_A,include_references=_E,include_context=_C,warn_skipped=_C):
	H=path;F=lang_ext;E=symbols;G=[];C={A:Capability.NONE for A in E};M=set(EXT_TO_LANG_PKG.keys());K=SymbolFinder(E,include_references,include_context)
	if H.is_dir():
		for D in sorted(H.rglob('*')):
			if not D.is_file():continue
			if F is _A and D.suffix.lower()not in M:continue
			I,B=K.search_file(D,F)
			for A in E:
				J=C[A]
				if CAP_ORDER[B]>CAP_ORDER[J]:C[A]=B
				G.extend(I.get(A,[]))
			if B is Capability.NONE and warn_skipped:L=_lang_load_errors.get((F or D.suffix).lower(),'');N=f": {L}"if L else'';print(f"warning: grammar unavailable for {D}{N}",file=sys.stderr)
	else:
		I,B=K.search_file(H,F)
		for A in E:
			J=C[A]
			if CAP_ORDER[B]>CAP_ORDER[J]:C[A]=B
			G.extend(I.get(A,[]))
	G.sort(key=lambda u:(u.file,u.start_line,u.symbol));return G,C
def fetch_source(path,start_line,end_line,context=0):
	E=end_line;D=start_line;C=context
	try:L=path.read_bytes()
	except OSError:return''
	M=L.replace(_m,_H).replace(_n,_H);B=M.decode(_T,errors=_U).splitlines();F=len(B);G=max(0,D-1);H=min(F,E);I=B[G:H]
	if C<=0:return _X.join(I)
	N=max(0,D-1-C);J=B[N:G];O=min(F,E+C);K=B[H:O];A=[]
	if J:A.extend(J);A.append('')
	A.extend(I)
	if K:A.append('');A.extend(K)
	return _X.join(A)
_SEARCH_CONTEXT_LINES=3
def format_search_results(usages,*,context_lines=_SEARCH_CONTEXT_LINES,show_defs=_E,show_refs=_C,raw=_E):
	O=context_lines;I=usages;E=raw
	if not I:return _AN
	J=[A for A in I if A.kind==_a];K=[A for A in I if A.kind!=_a and(show_refs or A.kind!=_N)];B=[]
	if show_defs and J:
		if not E:B.append(f"\n── Definitions ({len(J)}) "+'─'*50)
		for A in J:
			P=fetch_source(Path(A.file),A.start_line,A.end_line)
			if E:B.append(f"# DEF {A.symbol}  {A.file}:{A.start_line}-{A.end_line}");B.append(P);B.append('')
			else:
				B.append(f"\n  definition  {A.symbol}  {A.file}:{A.start_line}-{A.end_line}")
				for X in P.splitlines():B.append(f"    {X}")
				B.append('')
	if K:
		L=defaultdict(list)
		for A in K:L[A.file].append(A)
		if not E:B.append(f"\n── Uses ({len(K)}) "+'─'*50)
		for G in sorted(L):
			Q=L[G];Y=Path(G)
			if not E:R='─'*60;B.append(f"\n{R}\n  {G}\n{R}")
			else:B.append(f"\n# {G}")
			try:M=Y.read_bytes().replace(_m,_H).replace(_n,_H).decode(_T,errors=_U).splitlines()
			except OSError:
				for A in Q:B.append(f"  {A.kind:<12} {A.name_line}:{A.name_col}  {A.symbol}")
				continue
			N=len(M);D=[]
			for A in Q:
				S=max(1,A.start_line-O);T=min(N,A.end_line+O)
				if D and S<=D[-1][1]+1:Z,a,b=D[-1];D[-1]=Z,max(a,T),b+[A]
				else:D.append((S,T,[A]))
			for(F,H,U)in D:
				V=', '.join(f"{A.kind}({A.symbol}) @{A.name_line}:{A.name_col}"for A in U);W=f"{F}-{H}"if H!=F else str(F)
				if E:
					B.append(f"\n# {W}  |  {V}")
					for C in range(F,H+1):B.append(M[C-1]if C<=N else'')
				else:
					B.append(f"\n  # {W}  |  {V}");c={B for A in U for B in range(A.start_line,A.end_line+1)}
					for C in range(F,H+1):d=M[C-1]if C<=N else'';e='>'if C in c else' ';B.append(f"  {e} {C:5d}  {d}")
	return _X.join(B)
KIND_COLOR={_a:_AO,_S:_AP,'call':_AQ,'import':_R,_N:'\x1b[0;37m'}
OUTLINE_KIND_COLOR={_V:_AQ,_A0:_AO,_z:'\x1b[0;34m',_J:_AP,_A1:'\x1b[0;33m',_W:_R,'struct':_R,'enum':_R,'trait':_R,_AJ:_R,_AM:'\x1b[1;31m',_c:'\x1b[0;36m'}
RESET='\x1b[0m'
def print_outline(items,use_color=_E,file=sys.stdout):
	D=items;B=file
	if not D:print('No symbols found.',file=B);return
	E=_A
	for A in D:
		if A.file!=E:print(f"\n{A.file}",file=B);print('─'*min(len(A.file),80),file=B);E=A.file
		C=''
		if A.entry_point:C+=' [entry]'
		if A.exported:C+=' [exported]'
		if use_color:F=OUTLINE_KIND_COLOR.get(A.kind,'')+f"{A.kind:<12}"+RESET
		else:F=f"{A.kind:<12}"
		G=f"{A.start_line}:{A.start_col}–{A.end_line}:{A.end_col}";print(f"  {F} {A.name:<30} {G}{C}",file=B)
		if A.context:
			for H in A.context.split(_X):print(f"    | {H}",file=B)
def print_usages(usages,use_color=_E,file=sys.stdout):
	D=usages;B=file
	if not D:print(_AN,file=B);return
	E=_A
	for A in D:
		if A.symbol!=E:F=f"── {A.symbol} ";print(f"\n{F}{"─"*max(0,80-len(F))}",file=B);print(f"  {"KIND":<12} {"NAME AT":<16} {"FULL SPAN":<26} FILE",file=B);E=A.symbol
		G=f"{A.name_line}:{A.name_col}";H=f"{A.start_line}:{A.start_col}–{A.end_line}:{A.end_col}";C=A.kind;I=KIND_COLOR.get(C,'')+f"{C:<12}"+RESET if use_color else f"{C:<12}";print(f"  {I} {G:<16} {H:<26} {A.file}",file=B)
		if A.context:
			for J in A.context.split(_X):print(f"    | {J}",file=B)
def _warn(msg):print(f"warning: {msg}",file=sys.stderr)
def build_arg_parser():B='store_true';A=argparse.ArgumentParser(prog='sittree',description='Outline or search a codebase using tree-sitter.\n\n  python sittree.py <path>              — outline top-level symbols\n  python sittree.py <path> sym [sym ...] — search for symbol usages\n\n  Symbols are matched against *unqualified* identifier tokens. For convenience,\n  fully qualified names (e.g. "ClassName.method") are accepted — the tool\n  automatically uses the final component ("method") for matching but reports\n  results under the original qualified name.',formatter_class=argparse.RawDescriptionHelpFormatter);A.add_argument('path',help='File or directory to analyse');A.add_argument('symbols',nargs='*',metavar='symbol',help='Symbol names to search for (omit to get an outline)');A.add_argument('--lang',metavar='EXT_OR_NAME',default=_A);A.add_argument('--json',action=B,help='JSON array output (always a list)');A.add_argument('--no-color',action=B);A.add_argument('--no-references',action=B,help='Omit bare reference hits (search mode only)');A.add_argument('--warn-skipped',action=B,help='Warn about files whose grammar failed to load');A.add_argument('--kinds',metavar='K',nargs='+',choices=VALID_KINDS,default=_A,help='Filter search results by kind');A.add_argument('--depth',type=int,default=1,help='Max depth for outline (default: 1 = root symbols only)');A.add_argument('--context',action=B,help='Include surrounding source lines in output');return A
def resolve_lang_ext(arg):
	A=arg
	if A is _A:return
	B=A if A.startswith('.')else'.'+A
	if B in EXT_TO_LANG_PKG:return B
	return LANG_NAME_TO_EXT.get(A.lower())
def main(argv=_A):
	A=build_arg_parser().parse_args(argv);C=Path(A.path)
	if not C.exists():print(f"error: '{C}' does not exist.",file=sys.stderr);return 1
	E=resolve_lang_ext(A.lang);F=not A.no_color and sys.stdout.isatty()
	if not A.symbols:
		D=outline_path(C,E,max_depth=A.depth,include_context=A.context)
		if A.json:print(json.dumps([A.as_dict()for A in D],indent=2))
		else:print_outline(D,F)
		if not D and _lang_load_errors:return 2
		return 0
	B,H=search_symbols(A.symbols,C,lang_ext=E,include_references=not A.no_references,include_context=A.context,warn_skipped=A.warn_skipped);G=_C
	for(I,J)in H.items():
		if J is Capability.NONE:_warn(f"'{I}': no matching identifiers found (grammar may be unsupported for this file type)");G=_E
	if A.kinds:B=[B for B in B if B.kind in A.kinds]
	if A.json:print(json.dumps([A.as_dict()for A in B],indent=2))
	else:print_usages(B,F)
	if G and not B:return 2
	return 0
if __name__=='__main__':sys.exit(main())
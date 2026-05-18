"""
LLM实体/关系提取管道

移植自 MedGraphRAG:
- nano_graphrag/prompt.py → PROMPTS["entity_extraction"](第213-313行)
- nano_graphrag/prompt.py → PROMPTS["entiti_continue_extraction"](第334-336行)
- nano_graphrag/prompt.py → PROMPTS["entiti_if_loop_extraction"](第338-340行)
- nano_graphrag/prompt.py → PROMPTS["summarize_entity_descriptions"](第317-330行)
- nano_graphrag/_op.py → extract_entities()(第268-304行) + _process_single_content()(第244-266行)
- nano_graphrag/_op.py → _handle_single_entity_extraction()(第81-99行) + _handle_single_relationship_extraction()(第102-122行)
- nano_graphrag/_utils.py → split_string_by_multi_markers()(第77-82行) + clean_str()(第94-102行) + is_float_regex()(第69-70行)

适配改造:
- entity_types扩展为肝病领域12种类型（含Gene/Procedure/Complication）
- 强制类型约束Prompt + 类型归一化函数
- 实体数量引导（5-20实体/5-15关系）
- 一步提取：实体+关系+差异诊断+矛盾排除
- 跨Chunk实体去重+共参照关系推断
- 输出语言改为中文
- LLM调用集成kg_cache缓存
- 关系类型推断映射为8种诊断KG关系

使用示例：
    from core.kg.kg_extractor import KGExtractor
    extractor = KGExtractor()
    result = await extractor.extract(chunks)
"""

import asyncio
import html
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from loguru import logger

from core.kg.kg_schema import (
    DiseaseNode, FeatureNode, RelationEdge, ExtractionResult,
    FeatureCategory, RelationType, EvidenceLevel, GuidelineNode,
    DifferentialEdge, ContradictEdge,
)

TUPLE_DELIMITER = "<|>"
RECORD_DELIMITER = "##"
COMPLETION_DELIMITER = "<|COMPLETE|>"

ENTITY_TYPES = "LiverDisease, Phenotype, LabTest, Imaging, Treatment, Drug, Biomarker, ClinicalGuideline, Anatomy, Gene, Procedure, Complication"

ENTITY_EXTRACTION_PROMPT = """-Goal-
Given a medical text document about liver disease, identify all medical entities, their relationships, differential diagnoses, and contradiction/exclusion criteria.

-Steps-
1. Identify all entities. For each identified entity, extract the following information:
- entity_name: Name of the entity, capitalized
- entity_type: You MUST classify each entity into EXACTLY one of these types: [{entity_types}]. If an entity does not clearly fit any type, choose the closest match. Do NOT invent new types.
- entity_description: Comprehensive description of the entity's attributes and activities
Format each entity as ("entity"{tuple_delimiter}<entity_name>{tuple_delimiter}<entity_type>{tuple_delimiter}<entity_description>)

2. From the entities identified in step 1, identify all pairs of (source_entity, target_entity) that are *clearly related* to each other.
For each pair of related entities, extract the following information:
- source_entity: name of the source entity, as identified in step 1
- target_entity: name of the target entity, as identified in step 1
- relationship_description: explanation as to why you think the source entity and the target entity are related to each other
- relationship_strength: a numeric score indicating strength of the relationship between the source entity and target entity
Format each relationship as ("relationship"{tuple_delimiter}<source_entity>{tuple_delimiter}<target_entity>{tuple_delimiter}<relationship_description>{tuple_delimiter}<relationship_strength>)

3. Identify differential diagnosis relationships between diseases. For each pair of diseases that need to be differentiated:
- disease_a: name of the first disease
- disease_b: name of the second disease to differentiate from disease_a
- distinguishing_features: features that distinguish disease_a from disease_b (semicolon-separated)
- overlap_features: features shared by both diseases (semicolon-separated)
- difficulty: how difficult the differentiation is (easy, moderate, or hard)
Format each differential as ("differential"{tuple_delimiter}<disease_a>{tuple_delimiter}<disease_b>{tuple_delimiter}<distinguishing_features>{tuple_delimiter}<overlap_features>{tuple_delimiter}<difficulty>)

4. Identify contradiction/exclusion criteria - features that, when present in a specific condition, contradict or exclude a disease diagnosis:
- feature: name of the clinical feature or test result
- disease: name of the disease being contradicted/excluded
- contradict_condition: the specific condition that contradicts the diagnosis (e.g., "ceruloplasmin >= 0.20 g/L")
- strength: how strongly this contradicts the diagnosis (strong or moderate)
Format each contradiction as ("contradict"{tuple_delimiter}<feature>{tuple_delimiter}<disease>{tuple_delimiter}<contradict_condition>{tuple_delimiter}<strength>)

5. Aim to identify 5-20 entities and 5-15 relationships per text segment. Focus on the most clinically significant entities rather than exhaustive extraction. Only extract differentials and contradictions when they are clearly stated in the text.

6. Return output in Chinese as a single list of all the entities, relationships, differentials, and contradictions identified in steps 1-4. Use **{record_delimiter}** as the list delimiter.

7. When finished, output {completion_delimiter}

-Real Data-
Entity_types: {entity_types}
Text: {input_text}
Output:"""

GLEANING_CONTINUE_PROMPT = """MANY entities were missed in the last extraction. Add them below using the same format:
"""

GLEANING_IF_LOOP_PROMPT = """It appears some entities may have still been missed. Answer YES | NO if there are still entities that need to be added.
"""

ENTITY_SUMMARY_PROMPT = """You are a helpful assistant responsible for generating a comprehensive summary of the data provided below.
Given one or two entities, and a list of descriptions, all related to the same entity or group of entities.
Please concatenate all of these into a single, comprehensive description. Make sure to include information collected from all the descriptions.
If the provided descriptions are contradictory, please resolve the contradictions and provide a single, coherent summary.
Make sure it is written in third person, and include the entity names so we the have full context.

#######
-Data-
Entities: {entity_name}
Description List: {description_list}
#######
Output:
"""

RELATION_TYPE_MAP = {
    "is_a": ["属于", "归类", "是一种", "is a", "subtype of", "belongs to"],
    "has_manifestation": ["表现为", "症状", "symptom", "presents with", "manifests", "出现", "伴有"],
    "has_diagnostic_key": ["诊断标准", "关键特征", "diagnostic criteria", "key feature", "诊断依据", "确诊"],
    "differential_from": ["鉴别", "区分", "differential", "distinguish", "differentiate", "鉴别诊断"],
    "contradicts": ["排除", "否定", "contradicts", "excludes", "rules out", "不支持"],
    "associated_gene": ["基因", "突变", "gene", "mutation", "genetic", "遗传"],
    "guided_by": ["指南", "推荐", "guideline", "recommended", "according to", "建议"],
    "synonym_of": ["同义", "又称", "synonym", "also known as", "aka", "又名"],
}

ENTITY_TYPE_ALIASES: Dict[str, str] = {
    "MUTATION": "GENE",
    "GENETIC_MARKER": "GENE",
    "GENETIC_VARIANT": "GENE",
    "ALLELE": "GENE",
    "SURGERY": "PROCEDURE",
    "LIVER_TRANSPLANT": "PROCEDURE",
    "TRANSPLANT": "PROCEDURE",
    "BIOPSY": "PROCEDURE",
    "OPERATION": "PROCEDURE",
    "COMORBIDITY": "COMPLICATION",
    "ADVERSE_EFFECT": "COMPLICATION",
    "SIDE_EFFECT": "COMPLICATION",
    "SEQUELA": "COMPLICATION",
    "SIGN": "PHENOTYPE",
    "SYMPTOM": "PHENOTYPE",
    "CLINICAL_SIGN": "PHENOTYPE",
    "MANIFESTATION": "PHENOTYPE",
    "TEST": "LABTEST",
    "LABORATORY": "LABTEST",
    "LABORATORY_TEST": "LABTEST",
    "BLOOD_TEST": "LABTEST",
    "EXAMINATION": "LABTEST",
    "SCAN": "IMAGING",
    "RADIOLOGY": "IMAGING",
    "ULTRASOUND": "IMAGING",
    "MRI": "IMAGING",
    "CT": "IMAGING",
    "MEDICATION": "DRUG",
    "PHARMACEUTICAL": "DRUG",
    "THERAPY": "TREATMENT",
    "INTERVENTION": "TREATMENT",
    "MANAGEMENT": "TREATMENT",
    "DISEASE": "LIVERDISEASE",
    "CONDITION": "LIVERDISEASE",
    "DISORDER": "LIVERDISEASE",
    "GUIDELINE": "CLINICALGUIDELINE",
    "RECOMMENDATION": "CLINICALGUIDELINE",
    "ORGAN": "ANATOMY",
    "BODY_STRUCTURE": "ANATOMY",
    "MARKER": "BIOMARKER",
    "INDICATOR": "BIOMARKER",
}

ENTITY_TYPE_TO_FEATURE_CATEGORY: Dict[str, FeatureCategory] = {
    "PHENOTYPE": FeatureCategory.SYMPTOM,
    "LABTEST": FeatureCategory.LAB,
    "IMAGING": FeatureCategory.IMAGING,
    "BIOMARKER": FeatureCategory.LAB,
    "TREATMENT": FeatureCategory.SPECIAL_TEST,
    "DRUG": FeatureCategory.SPECIAL_TEST,
    "ANATOMY": FeatureCategory.PHYSICAL,
    "GENE": FeatureCategory.GENETIC,
    "PROCEDURE": FeatureCategory.SPECIAL_TEST,
    "COMPLICATION": FeatureCategory.SYMPTOM,
}

VALID_ENTITY_TYPES = {
    "LIVERDISEASE", "PHENOTYPE", "LABTEST", "IMAGING", "TREATMENT",
    "DRUG", "BIOMARKER", "CLINICALGUIDELINE", "ANATOMY", "GENE",
    "PROCEDURE", "COMPLICATION",
}


def normalize_entity_type(raw_type: str) -> str:
    normalized = raw_type.strip().upper()
    normalized = re.sub(r"[\s\-_]+", "_", normalized)
    if normalized in VALID_ENTITY_TYPES:
        return normalized
    if normalized in ENTITY_TYPE_ALIASES:
        return ENTITY_TYPE_ALIASES[normalized]
    for alias, standard in ENTITY_TYPE_ALIASES.items():
        if alias in normalized or normalized in alias:
            return standard
    return "PHENOTYPE"


def split_string_by_multi_markers(content: str, markers: List[str]) -> List[str]:
    if not markers:
        return [content]
    results = re.split("|".join(re.escape(marker) for marker in markers), content)
    return [r.strip() for r in results if r.strip()]


def clean_str(input_val: Any) -> str:
    if not isinstance(input_val, str):
        return str(input_val)
    result = html.unescape(input_val.strip())
    return re.sub(r"[\x00-\x1f\x7f-\x9f]", "", result)


def is_float_regex(value: str) -> bool:
    return bool(re.match(r"^[-+]?[0-9]*\.?[0-9]+$", value.strip()))


def infer_relation_type(description: str, strength: float = 1.0) -> str:
    desc_lower = description.lower()
    for rel_type, keywords in RELATION_TYPE_MAP.items():
        for kw in keywords:
            if kw in desc_lower:
                return rel_type
    return "has_manifestation"


def parse_extraction_response(response: str) -> Dict[str, Any]:
    records = split_string_by_multi_markers(
        response, [RECORD_DELIMITER, COMPLETION_DELIMITER]
    )
    maybe_nodes: Dict[str, Dict] = {}
    maybe_edges: Dict[Tuple[str, str], Dict] = {}
    maybe_differentials: List[Dict] = []
    maybe_contradicts: List[Dict] = []

    for record in records:
        record_match = re.search(r"\((.*)\)", record)
        if record_match is None:
            continue
        record_content = record_match.group(1)
        record_attributes = split_string_by_multi_markers(
            record_content, [TUPLE_DELIMITER]
        )

        if len(record_attributes) >= 4 and record_attributes[0].strip().strip('"') == "entity":
            entity_name = clean_str(record_attributes[1]).upper()
            entity_type = clean_str(record_attributes[2]).upper()
            entity_description = clean_str(record_attributes[3])
            if entity_name.strip():
                if entity_name in maybe_nodes:
                    maybe_nodes[entity_name]["descriptions"].append(entity_description)
                else:
                    maybe_nodes[entity_name] = {
                        "entity_name": entity_name,
                        "entity_type": entity_type,
                        "descriptions": [entity_description],
                    }

        elif len(record_attributes) >= 5 and record_attributes[0].strip().strip('"') == "relationship":
            source = clean_str(record_attributes[1]).upper()
            target = clean_str(record_attributes[2]).upper()
            description = clean_str(record_attributes[3])
            strength = float(record_attributes[-1]) if is_float_regex(record_attributes[-1]) else 1.0
            if source.strip() and target.strip():
                key = tuple(sorted([source, target]))
                if key in maybe_edges:
                    maybe_edges[key]["descriptions"].append(description)
                    maybe_edges[key]["weight"] = max(maybe_edges[key]["weight"], strength)
                else:
                    maybe_edges[key] = {
                        "src_id": source,
                        "tgt_id": target,
                        "descriptions": [description],
                        "weight": strength,
                    }

        elif len(record_attributes) >= 5 and record_attributes[0].strip().strip('"') == "differential":
            disease_a = clean_str(record_attributes[1]).upper()
            disease_b = clean_str(record_attributes[2]).upper()
            distinguishing = clean_str(record_attributes[3])
            overlap = clean_str(record_attributes[4]) if len(record_attributes) > 4 else ""
            difficulty = clean_str(record_attributes[5]) if len(record_attributes) > 5 else "moderate"
            if disease_a.strip() and disease_b.strip():
                maybe_differentials.append({
                    "disease_a": disease_a,
                    "disease_b": disease_b,
                    "distinguishing_features": [f.strip() for f in distinguishing.split(";") if f.strip()],
                    "overlap_features": [f.strip() for f in overlap.split(";") if f.strip()],
                    "difficulty": difficulty.strip().lower() if difficulty.strip().lower() in ("easy", "moderate", "hard") else "moderate",
                })

        elif len(record_attributes) >= 4 and record_attributes[0].strip().strip('"') == "contradict":
            feature = clean_str(record_attributes[1]).upper()
            disease = clean_str(record_attributes[2]).upper()
            condition = clean_str(record_attributes[3])
            strength = clean_str(record_attributes[4]) if len(record_attributes) > 4 else "moderate"
            if feature.strip() and disease.strip():
                maybe_contradicts.append({
                    "feature_id": feature,
                    "disease_id": disease,
                    "contradict_condition": condition,
                    "strength": strength.strip().lower() if strength.strip().lower() in ("strong", "moderate") else "moderate",
                })

    return {
        "entities": maybe_nodes,
        "relationships": maybe_edges,
        "differentials": maybe_differentials,
        "contradicts": maybe_contradicts,
    }


class KGExtractor:
    def __init__(
        self,
        max_gleaning: int = 1,
        max_concurrent: int = 4,
    ):
        self.max_gleaning = max_gleaning
        self.max_concurrent = max_concurrent
        self._cache = None
        self._llm_client = None

    def _get_cache(self):
        if self._cache is None:
            from core.kg.kg_cache import KGCache
            self._cache = KGCache()
        return self._cache

    def _get_llm_client(self):
        if self._llm_client is None:
            from core.llm_client import get_llm_client
            self._llm_client = get_llm_client()
        return self._llm_client

    async def _call_llm(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history_messages: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        cache = self._get_cache()
        from core.kg.kg_cache import KGCache
        cache_key = KGCache.compute_key(prompt, "kg_extractor") if self._cache else None

        if cache_key:
            cached = cache.get(cache_key)
            if cached is not None:
                return cached.get("response", "")

        llm = self._get_llm_client()
        lc_messages = []

        if system_prompt:
            lc_messages.append(SystemMessage(content=system_prompt))

        if history_messages:
            for msg in history_messages:
                if msg["role"] == "system":
                    lc_messages.append(SystemMessage(content=msg["content"]))
                elif msg["role"] == "assistant":
                    lc_messages.append(AIMessage(content=msg["content"]))
                else:
                    lc_messages.append(HumanMessage(content=msg["content"]))

        lc_messages.append(HumanMessage(content=prompt))

        try:
            response = await llm.ainvoke(lc_messages)
            response_text = response.content if hasattr(response, 'content') else str(response)

            if cache_key:
                cache.put(cache_key, {"response": response_text})

            return response_text
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise

    async def extract_single_chunk(
        self,
        chunk_text: str,
        chunk_id: str = "",
        source_file: Optional[str] = None,
        page_number: Optional[int] = None,
    ) -> ExtractionResult:
        text_input = chunk_text[:3000]
        prompt = ENTITY_EXTRACTION_PROMPT.format(
            entity_types=ENTITY_TYPES,
            tuple_delimiter=TUPLE_DELIMITER,
            record_delimiter=RECORD_DELIMITER,
            completion_delimiter=COMPLETION_DELIMITER,
            input_text=text_input,
        )

        try:
            first_response = await self._call_llm(prompt)
        except Exception as e:
            logger.error(f"Entity extraction failed for chunk {chunk_id}: {e}")
            return ExtractionResult(
                raw_text=chunk_text,
                chunk_id=chunk_id,
                source_file=source_file,
                page_number=page_number,
                validation_passed=False,
                validation_errors=[str(e)],
            )

        all_responses = [first_response]
        history: List[Dict[str, str]] = [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": first_response},
        ]

        for gleaning_round in range(self.max_gleaning):
            continue_prompt = GLEANING_CONTINUE_PROMPT
            try:
                continue_response = await self._call_llm(
                    prompt=continue_prompt,
                    system_prompt="Continue extracting entities from the previous text.",
                    history_messages=history,
                )
            except Exception as e:
                logger.warning(f"Gleaning round {gleaning_round + 1} failed: {e}")
                break

            history.append({"role": "user", "content": continue_prompt})
            history.append({"role": "assistant", "content": continue_response})

            if_loop_prompt = GLEANING_IF_LOOP_PROMPT
            try:
                if_loop_response = await self._call_llm(
                    prompt=if_loop_prompt,
                    system_prompt="Answer YES or NO only.",
                    history_messages=history,
                )
            except Exception as e:
                logger.warning(f"Gleaning loop check failed: {e}")
                break

            if "NO" in if_loop_response.upper():
                break

            all_responses.append(continue_response)

        combined_response = RECORD_DELIMITER.join(all_responses)
        parsed = parse_extraction_response(combined_response)

        result = self._to_extraction_result(
            parsed, chunk_text, chunk_id, source_file, page_number
        )

        entity_count = len(result.disease_nodes) + len(result.feature_nodes) + len(result.guideline_nodes)
        if entity_count < 3:
            logger.warning(f"Chunk {chunk_id}: only {entity_count} entities extracted (low)")
        elif entity_count > 30:
            logger.warning(f"Chunk {chunk_id}: {entity_count} entities extracted (high, may contain noise)")

        return result

    async def extract(
        self,
        chunks: List[Any],
    ) -> ExtractionResult:
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def _process_with_semaphore(chunk):
            async with semaphore:
                chunk_text = chunk.content if hasattr(chunk, 'content') else str(chunk)
                chunk_id = chunk.chunk_id if hasattr(chunk, 'chunk_id') else ""
                source_file = chunk.source if hasattr(chunk, 'source') else None
                page_number = chunk.page_number if hasattr(chunk, 'page_number') else None
                return await self.extract_single_chunk(
                    chunk_text, chunk_id, source_file, page_number
                )

        tasks = [_process_with_semaphore(chunk) for chunk in chunks]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        merged = ExtractionResult()
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Chunk {i} extraction failed: {result}")
            else:
                merged = self._merge_with_dedup(merged, result)

        logger.info(
            f"Extraction complete: {len(merged.disease_nodes)} diseases, "
            f"{len(merged.feature_nodes)} features, {len(merged.relation_edges)} relations, "
            f"{len(merged.differential_edges)} differentials, {len(merged.contradict_edges)} contradicts"
        )
        return merged

    def _merge_with_dedup(
        self, base: ExtractionResult, new: ExtractionResult
    ) -> ExtractionResult:
        before_entities = len(base.disease_nodes) + len(base.feature_nodes)
        before_relations = len(base.relation_edges)

        disease_map: Dict[str, DiseaseNode] = {}
        for d in base.disease_nodes:
            disease_map[d.disease_id.upper()] = d
        for d in new.disease_nodes:
            key = d.disease_id.upper()
            if key in disease_map:
                existing = disease_map[key]
                if d.description and (not existing.description or len(d.description) > len(existing.description)):
                    disease_map[key] = d
            else:
                disease_map[key] = d

        feature_map: Dict[str, FeatureNode] = {}
        for f in base.feature_nodes:
            feature_map[f.name.upper()] = f
        synonym_edges: List[RelationEdge] = []
        for f in new.feature_nodes:
            key = f.name.upper()
            if key in feature_map:
                existing = feature_map[key]
                if f.is_core and not existing.is_core:
                    feature_map[key] = f
                elif f.specificity > existing.specificity:
                    feature_map[key] = f
                if existing.feature_id != f.feature_id:
                    synonym_edges.append(RelationEdge(
                        source_id=existing.feature_id,
                        target_id=f.feature_id,
                        relation_type=RelationType.SYNONYM_OF,
                        confidence=0.9,
                        weight=0.9,
                        evidence=f"跨Chunk同名实体: {f.name}",
                    ))
            else:
                feature_map[key] = f

        guideline_map: Dict[str, GuidelineNode] = {}
        for g in base.guideline_nodes:
            guideline_map[g.guideline_id.upper()] = g
        for g in new.guideline_nodes:
            key = g.guideline_id.upper()
            if key not in guideline_map:
                guideline_map[key] = g

        relation_keys: Set[Tuple[str, str, str]] = set()
        all_relations = list(base.relation_edges)
        for r in base.relation_edges:
            relation_keys.add((r.source_id.upper(), r.target_id.upper(), r.relation_type.value))
        for r in new.relation_edges:
            key = (r.source_id.upper(), r.target_id.upper(), r.relation_type.value)
            if key not in relation_keys:
                all_relations.append(r)
                relation_keys.add(key)
        all_relations.extend(synonym_edges)

        diff_keys: Set[Tuple[str, str]] = set()
        all_diffs = list(base.differential_edges)
        for d in base.differential_edges:
            diff_keys.add((d.disease_a_id.upper(), d.disease_b_id.upper()))
        for d in new.differential_edges:
            key = (d.disease_a_id.upper(), d.disease_b_id.upper())
            if key not in diff_keys:
                all_diffs.append(d)
                diff_keys.add(key)

        contra_keys: Set[Tuple[str, str]] = set()
        all_contras = list(base.contradict_edges)
        for c in base.contradict_edges:
            contra_keys.add((c.feature_id.upper(), c.disease_id.upper()))
        for c in new.contradict_edges:
            key = (c.feature_id.upper(), c.disease_id.upper())
            if key not in contra_keys:
                all_contras.append(c)
                contra_keys.add(key)

        after_entities = len(disease_map) + len(feature_map)
        after_relations = len(all_relations)
        dedup_entities = before_entities + len(new.disease_nodes) + len(new.feature_nodes) - after_entities
        dedup_relations = before_relations + len(new.relation_edges) + len(synonym_edges) - after_relations

        if dedup_entities > 0 or dedup_relations > 0 or synonym_edges:
            logger.info(
                f"Merge dedup: -{dedup_entities} entities, -{dedup_relations} relations, "
                f"+{len(synonym_edges)} synonym edges"
            )

        return ExtractionResult(
            disease_nodes=list(disease_map.values()),
            feature_nodes=list(feature_map.values()),
            relation_edges=all_relations,
            guideline_nodes=list(guideline_map.values()),
            differential_edges=all_diffs,
            contradict_edges=all_contras,
            raw_text=base.raw_text or new.raw_text,
            chunk_id=base.chunk_id or new.chunk_id,
            source_file=base.source_file or new.source_file,
            page_number=base.page_number or new.page_number,
            extraction_model=base.extraction_model or new.extraction_model,
            validation_passed=base.validation_passed and new.validation_passed,
            validation_errors=base.validation_errors + new.validation_errors,
        )

    def _to_extraction_result(
        self,
        parsed: Dict[str, Any],
        raw_text: str,
        chunk_id: str,
        source_file: Optional[str],
        page_number: Optional[int],
    ) -> ExtractionResult:
        disease_nodes: List[DiseaseNode] = []
        feature_nodes: List[FeatureNode] = []
        guideline_nodes: List[GuidelineNode] = []
        relation_edges: List[RelationEdge] = []
        differential_edges: List[DifferentialEdge] = []
        contradict_edges: List[ContradictEdge] = []

        for entity_name, entity_data in parsed.get("entities", {}).items():
            raw_type = entity_data.get("entity_type", "").upper()
            entity_type = normalize_entity_type(raw_type)
            descriptions = entity_data.get("descriptions", [])
            description = descriptions[0] if descriptions else ""
            name = entity_data.get("entity_name", entity_name)

            if raw_type != entity_type and raw_type not in VALID_ENTITY_TYPES:
                logger.debug(f"Entity type normalized: {raw_type} -> {entity_type} for '{name}'")

            if entity_type == "LIVERDISEASE":
                disease_nodes.append(DiseaseNode(
                    disease_id=name,
                    name=name,
                    layer=EvidenceLevel.EL3,
                    description=description,
                    source=source_file,
                    source_page=page_number,
                ))
            elif entity_type == "CLINICALGUIDELINE":
                guideline_nodes.append(GuidelineNode(
                    guideline_id=name,
                    title=name,
                    description=description,
                    source_file=source_file,
                ))
            elif entity_type in ENTITY_TYPE_TO_FEATURE_CATEGORY:
                feature_nodes.append(FeatureNode(
                    feature_id=name,
                    name=name,
                    layer=EvidenceLevel.EL4D,
                    category=ENTITY_TYPE_TO_FEATURE_CATEGORY[entity_type],
                    description=description,
                    source=source_file,
                    source_page=page_number,
                ))
            else:
                feature_nodes.append(FeatureNode(
                    feature_id=name,
                    name=name,
                    layer=EvidenceLevel.EL4A,
                    category=FeatureCategory.SYMPTOM,
                    description=description,
                    source=source_file,
                    source_page=page_number,
                ))

        for key, edge_data in parsed.get("relationships", {}).items():
            src = edge_data.get("src_id", "")
            tgt = edge_data.get("tgt_id", "")
            descriptions = edge_data.get("descriptions", [])
            description = descriptions[0] if descriptions else ""
            weight = edge_data.get("weight", 1.0)

            rel_type_str = infer_relation_type(description, weight)
            try:
                rel_type = RelationType(rel_type_str)
            except ValueError:
                rel_type = RelationType.HAS_MANIFESTATION

            relation_edges.append(RelationEdge(
                source_id=src,
                target_id=tgt,
                relation_type=rel_type,
                confidence=weight,
                weight=weight,
                evidence=description,
                source=source_file,
                source_page=page_number,
            ))

        for diff_data in parsed.get("differentials", []):
            differential_edges.append(DifferentialEdge(
                disease_a_id=diff_data["disease_a"],
                disease_b_id=diff_data["disease_b"],
                distinguishing_features=diff_data.get("distinguishing_features", []),
                overlap_features=diff_data.get("overlap_features", []),
                difficulty=diff_data.get("difficulty", "moderate"),
                source=source_file,
            ))

        for contra_data in parsed.get("contradicts", []):
            strength = contra_data.get("strength", "moderate")
            contradict_edges.append(ContradictEdge(
                feature_id=contra_data["feature_id"],
                disease_id=contra_data["disease_id"],
                contradict_condition=contra_data.get("contradict_condition", ""),
                strength=strength,
                confidence=0.95 if strength == "strong" else 0.8,
                weight=2.0 if strength == "strong" else 1.5,
                source=source_file,
                source_page=page_number,
            ))

        return ExtractionResult(
            disease_nodes=disease_nodes,
            feature_nodes=feature_nodes,
            relation_edges=relation_edges,
            guideline_nodes=guideline_nodes,
            differential_edges=differential_edges,
            contradict_edges=contradict_edges,
            raw_text=raw_text,
            chunk_id=chunk_id,
            source_file=source_file,
            page_number=page_number,
            extraction_model="kg_extractor",
        )

check_grep:
	@grep -qF "GNU grep" || echo "you have to have gnu grep"

plant_uml_convert: # check_grep
	PLANTUML_LIMIT_SIZE=12348192 plantuml cacl2.plantuml
	grep -Pi "startuml|enduml|calc" cacl2.plantuml > cacl2_2.plantuml
	plantuml cacl2_2.plantuml
	open .
